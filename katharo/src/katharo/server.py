"""Loopback presentation adapter and composition root."""

import argparse
import json
import os
import secrets
import shutil
import threading
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from katharo.actions import Actions
from katharo.domain import ReviewError
from katharo.scanner import scan
from katharo.store import Store


class App:
    def __init__(self, home: Path):
        self.home = home.resolve()
        self.store = Store(self.home / "inventory.sqlite")
        self.actions = Actions(self.store)
        self.token = secrets.token_urlsafe(32)
        self.jobs: dict[str, dict] = {}
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.mutation_lock = threading.Lock()
        self.scan_lock = threading.Lock()
        self.port = 0

    def start_scan(self, request: dict) -> dict:
        if not self.scan_lock.acquire(blocking=False):
            raise ReviewError("A scan is already running. Cancel it or wait for it to finish.")
        job: dict[str, Any] = {
            "id": uuid4().hex,
            "status": "running",
            "phase": "Starting",
            "count": 0,
            "cancel": False,
        }
        self.jobs[job["id"]] = job

        def run():
            try:
                excluded = [self.home] + [Path(p["destination"]) for p in self.store.list("plan")]

                def progress(phase, count):
                    job.update(phase=phase, count=count)

                result = scan(
                    str(request.get("folder", "")),
                    bool(request.get("recursive", True)),
                    bool(request.get("documents", False)),
                    progress,
                    lambda: job["cancel"],
                    excluded,
                )
                self.store.save("scan", result)
                job.update(status=result["status"], scan_id=result["id"])
            except Exception as exc:
                job.update(status="failed", error=str(exc))
            finally:
                self.scan_lock.release()

        self.pool.submit(run)
        return job.copy()

    def dispatch(self, route: str, data: dict) -> dict | list:
        if route == "/api/scan":
            return self.start_scan(data)
        if route == "/api/job":
            return self.jobs[str(data["id"])].copy()
        if route == "/api/cancel":
            self.jobs[str(data["id"])]["cancel"] = True
            return {"ok": True}
        if route == "/api/scan-result":
            return self.store.get("scan", str(data["id"]))
        if route == "/api/history":
            return self.store.list("plan")
        if route == "/api/decision":
            record = {
                "id": str(data["scan_id"]) + ":" + str(data["group_id"]),
                "decision": str(data["decision"]),
            }
            self.store.save("decision", record)
            return {"ok": True}
        if route == "/api/prepare":
            with self.mutation_lock:
                return self.actions.prepare(
                    self.store.get("scan", str(data["scan_id"])),
                    list(data["selected"]),
                    str(data["destination"]),
                )
        if route == "/api/execute":
            if data.get("confirmed") is not True:
                raise ReviewError("Explicit plan confirmation is required.")
            with self.mutation_lock:
                return self.actions.execute(str(data["id"]))
        if route == "/api/restore":
            with self.mutation_lock:
                return self.actions.restore(str(data["id"]))
        if route == "/api/pick-folder":
            # The native picker runs in a separate process so Tk owns its main thread.
            import subprocess
            import sys

            script = "import tkinter as t; from tkinter import filedialog; r=t.Tk(); r.withdraw(); r.attributes('-topmost',True); print(filedialog.askdirectory(title='Choose a Katharo folder')); r.destroy()"
            output = subprocess.run(
                [sys.executable, "-c", script], capture_output=True, text=True, timeout=120
            )
            if output.returncode:
                raise ReviewError("Folder picker unavailable. Paste a folder path instead.")
            return {"folder": output.stdout.strip()}
        if route == "/api/info":
            default = Path.home() / "Downloads"
            usage = shutil.disk_usage(default if default.exists() else Path.home())
            return {
                "default_folder": str(default),
                "default_quarantine": str(Path.home() / "Katharo Quarantine"),
                "free": usage.free,
                "total": usage.total,
            }
        raise ReviewError("Unknown request.")


def handler_for(app: App):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, code: int, content: bytes, kind="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            )
            self.end_headers()
            self.wfile.write(content)

        def host_valid(self):
            return self.headers.get("Host") == f"127.0.0.1:{app.port}"

        def do_GET(self):
            if not self.host_valid():
                self.reply(403, b'{"error":"Invalid host"}')
                return
            route = urlparse(self.path).path
            if route == "/api/session":
                self.reply(200, json.dumps({"token": app.token}).encode())
                return
            names = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}
            if route not in names:
                self.reply(404, b'{"error":"Not found"}')
                return
            file = Path(__file__).parent / "web" / names[route]
            kind = {
                ".html": "text/html; charset=utf-8",
                ".js": "text/javascript; charset=utf-8",
                ".css": "text/css; charset=utf-8",
            }[file.suffix]
            self.reply(200, file.read_bytes(), kind)

        def do_POST(self):
            origin = self.headers.get("Origin")
            if (
                not self.host_valid()
                or origin not in {None, f"http://127.0.0.1:{app.port}"}
                or self.headers.get("X-Katharo-Token") != app.token
            ):
                self.reply(403, b'{"error":"Unauthorized local request"}')
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0 or length > 1024 * 1024:
                    raise ReviewError("Request too large.")
                data = json.loads(self.rfile.read(length))
                result = app.dispatch(urlparse(self.path).path, data)
                self.reply(200, json.dumps(result).encode())
            except (ValueError, KeyError, OSError) as exc:
                self.reply(400, json.dumps({"error": str(exc)}).encode())
            except Exception:
                self.reply(500, b'{"error":"Operation failed. No automatic retry was performed."}')

    return Handler


def main():
    parser = argparse.ArgumentParser(description="Katharo local file review")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "Katharo",
    )
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    app = App(args.data_dir)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(app))
    app.port = server.server_port
    url = f"http://127.0.0.1:{app.port}"
    print(f"Katharo is ready: {url}", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        for job in app.jobs.values():
            job["cancel"] = True
        app.pool.shutdown(wait=False, cancel_futures=True)


if __name__ == "__main__":
    main()
