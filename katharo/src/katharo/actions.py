"""Persisted quarantine workflow. No permanent-delete operation is exposed."""

import json
import os
import shutil
import time
from pathlib import Path
from uuid import uuid4

from katharo.domain import ReviewError, validate_selection
from katharo.filesystem import equal_bytes, guarded_path, hash_file, protected, revalidate
from katharo.store import Store


class Actions:
    def __init__(self, store: Store):
        self.store = store

    def prepare(self, scan: dict, selected: list[str], destination: str) -> dict:
        if scan["status"] != "complete":
            raise ReviewError("Finish a scan before preparing a plan.")
        chosen = set(selected)
        validate_selection(scan["groups"], chosen)
        root = Path(scan["root"])
        if not destination.strip() or not Path(destination).expanduser().is_absolute():
            raise ReviewError("Enter an absolute quarantine folder path.")
        target = guarded_path(Path(destination).expanduser())
        if not target.is_absolute() or target == Path(target.anchor) or protected(target):
            raise ReviewError(
                "Choose a personal quarantine folder, not a drive root or system folder."
            )
        if target.is_relative_to(root) or root.is_relative_to(target):
            raise ReviewError("Quarantine must be outside the scanned folder and its parents.")
        if target.exists() and not target.is_dir():
            raise ReviewError("Quarantine destination must be a folder.")
        records = {f["id"]: f for f in scan["files"]}
        items = []
        for group in scan["groups"]:
            if group["kind"] != "exact":
                continue
            keeper = next((f for f in group["files"] if f["id"] not in chosen), None)
            for file in group["files"]:
                if file["id"] in chosen:
                    items.append(
                        {
                            "id": file["id"],
                            "file": records[file["id"]],
                            "keeper": keeper,
                            "status": "planned",
                            "error": "",
                        }
                    )
        plan = {
            "id": uuid4().hex,
            "scan_id": scan["id"],
            "root": str(root),
            "destination": str(target),
            "created": time.time(),
            "status": "prepared",
            "items": items,
            "bytes": sum(x["file"]["size"] for x in items),
        }
        self.store.save("plan", plan)
        return plan

    def journal(self, plan: dict) -> None:
        self.store.save("plan", plan)
        manifest = Path(plan["destination"]) / plan["id"] / "manifest.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        guarded_path(manifest.parent)
        temp = manifest.with_suffix(".tmp")
        with temp.open("w", encoding="utf-8") as stream:
            json.dump(plan, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, manifest)

    def execute(self, plan_id: str) -> dict:
        plan = self.store.get("plan", plan_id)
        if plan["status"] != "prepared":
            raise ReviewError("This plan has already been attempted. Review history instead.")
        root = Path(plan["root"])
        target = guarded_path(Path(plan["destination"]))
        plan["status"] = "executing"
        self.journal(plan)
        for item in plan["items"]:
            try:
                source = revalidate(item["file"], root)
                keeper = revalidate(item["keeper"], root)
                if not equal_bytes(source, keeper):
                    raise ReviewError("Byte verification failed.")
                dest = target / plan["id"] / item["id"] / source.name
                guarded_path(dest.parent)
                dest.parent.mkdir(parents=True, exist_ok=False)
                item["quarantine_path"] = str(dest)
                item["status"] = "moving"
                self.journal(plan)
                if source.stat().st_dev == dest.parent.stat().st_dev:
                    guarded_path(source, root)
                    os.rename(source, dest)
                else:
                    if shutil.disk_usage(dest.parent).free < source.stat().st_size + 1024 * 1024:
                        raise ReviewError("Insufficient space on quarantine drive.")
                    with source.open("rb") as src, dest.open("xb") as dst:
                        shutil.copyfileobj(src, dst, 1024 * 1024)
                        dst.flush()
                        os.fsync(dst.fileno())
                    if hash_file(dest) != item["file"]["digest"]:
                        raise ReviewError("Quarantine copy verification failed; original retained.")
                    revalidate(item["file"], root)
                    revalidate(item["keeper"], root)
                    source.unlink()
                item["status"] = "quarantined"
            except (OSError, ValueError) as exc:
                item["status"] = "failed"
                item["error"] = str(exc)
            self.journal(plan)
        plan["status"] = (
            "completed" if all(x["status"] == "quarantined" for x in plan["items"]) else "partial"
        )
        self.journal(plan)
        return plan

    def restore(self, plan_id: str) -> dict:
        plan = self.store.get("plan", plan_id)
        for item in plan["items"]:
            if item["status"] not in {"quarantined", "moving", "restoring"}:
                continue
            try:
                original = guarded_path(Path(item["file"]["path"]), Path(plan["root"]))
                source = guarded_path(
                    Path(item["quarantine_path"]), Path(plan["destination"]) / plan["id"]
                )
                if original.exists():
                    raise ReviewError(
                        "Original location is occupied. Restore will not overwrite it."
                    )
                if hash_file(source) != item["file"]["digest"]:
                    raise ReviewError("Quarantined content changed. Manual review required.")
                original.parent.mkdir(parents=True, exist_ok=True)
                item["status"] = "restoring"
                self.journal(plan)
                # Exclusive creation makes restore refuse concurrent target creation.
                with source.open("rb") as src, original.open("xb") as dst:
                    shutil.copyfileobj(src, dst, 1024 * 1024)
                    dst.flush()
                    os.fsync(dst.fileno())
                if hash_file(original) != item["file"]["digest"]:
                    raise ReviewError("Restored copy verification failed; quarantine retained.")
                source.unlink()
                item["status"] = "restored"
                item["error"] = ""
            except (OSError, ValueError) as exc:
                item["error"] = str(exc)
            self.journal(plan)
        plan["status"] = (
            "restored"
            if all(x["status"] in {"restored", "failed"} for x in plan["items"])
            else "partial"
        )
        self.journal(plan)
        return plan
