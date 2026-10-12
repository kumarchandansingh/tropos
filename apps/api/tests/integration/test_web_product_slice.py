from __future__ import annotations

import json
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tropos.core.adapters.retrieval.sqlite_fts import SQLiteFtsKnowledgeRetriever
from tropos.core.application.retrieval.models import (
    KnowledgeSearchRequest,
    RetrievalAccessContext,
)
from tropos.web import build_server


def _start_server(tmp_path: Path) -> tuple[ThreadingHTTPServer, str, Thread]:
    server = build_server(
        host="127.0.0.1",
        port=0,
        database_path=tmp_path / "tropos.db",
        trace_path=tmp_path / "traces.jsonl",
    )
    host, port = cast(tuple[str, int], server.server_address)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://{host}:{port}", thread


def _read_json(request: Request) -> tuple[int, dict[str, object]]:
    with urlopen(request, timeout=3) as response:
        parsed = json.loads(response.read())
        assert isinstance(parsed, dict)
        return response.status, cast(dict[str, object], parsed)


def test_web_shell_exposes_sources_and_resolve_workspaces(tmp_path: Path) -> None:
    server, base, thread = _start_server(tmp_path)
    try:
        with urlopen(base + "/", timeout=3) as response:
            html = response.read().decode()
        assert response.status == 200
        assert "Sources & Ingestion" in html
        assert ">Resolve<" in html
        assert "Sufficiency remains visibly unvalidated" in html
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


def test_web_ingest_creates_searchable_governed_knowledge(tmp_path: Path) -> None:
    database = tmp_path / "tropos.db"
    server = build_server(
        host="127.0.0.1",
        port=0,
        database_path=database,
        trace_path=tmp_path / "traces.jsonl",
    )
    host, port = cast(tuple[str, int], server.server_address)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = Request(
            f"http://{host}:{port}/api/ingest?filename=runbook.md&tenant=tenant-a",
            data=b"# Rotation\n\nRestart the edge service after certificate rotation.",
            method="POST",
            headers={"Content-Type": "text/markdown"},
        )
        status, payload = _read_json(request)

        assert status == 200
        assert payload["status"] == "available"
        assert payload["outcome"] == "VERSION_CREATED"
        chunks_written = payload["chunks_written"]
        assert isinstance(chunks_written, int)
        assert chunks_written > 0

        results = SQLiteFtsKnowledgeRetriever(database).search(
            KnowledgeSearchRequest(
                query="certificate rotation",
                access=RetrievalAccessContext(tenant_id="tenant-a"),
            )
        )
        assert results
        assert results[0].chunk.source_record_id == "runbook.md"
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


def test_web_ingest_rejects_unsafe_or_unsupported_filename(tmp_path: Path) -> None:
    server, base, thread = _start_server(tmp_path)
    try:
        request = Request(
            base + "/api/ingest?filename=secret.exe",
            data=b"not allowed",
            method="POST",
        )
        try:
            urlopen(request, timeout=3)
        except HTTPError as exc:
            assert exc.code == 422
        else:
            raise AssertionError("unsupported file must be rejected")
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


def test_web_trace_detail_reads_exact_trace(tmp_path: Path) -> None:
    trace_path = tmp_path / "traces.jsonl"
    trace_path.write_text(
        json.dumps(
            {
                "trace_id": "trace_demo",
                "request_id": "request_demo",
                "outcome": "ANSWERED",
                "spans": [
                    {
                        "name": "resolve.retrieval",
                        "status": "OK",
                        "attributes": {"result_count": 1},
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    server = build_server(
        host="127.0.0.1",
        port=0,
        database_path=tmp_path / "tropos.db",
        trace_path=trace_path,
    )
    host, port = cast(tuple[str, int], server.server_address)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(f"http://{host}:{port}/api/traces/trace_demo", timeout=3) as response:
            parsed = json.loads(response.read())

        assert response.status == 200
        assert isinstance(parsed, dict)
        payload = cast(dict[str, object], parsed)
        assert payload["outcome"] == "ANSWERED"
        spans = payload["spans"]
        assert isinstance(spans, list)
        assert spans
        first = spans[0]
        assert isinstance(first, dict)
        assert first["name"] == "resolve.retrieval"
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()
