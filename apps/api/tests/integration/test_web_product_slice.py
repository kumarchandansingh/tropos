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


def test_web_shell_exposes_sources_resolve_and_observability(tmp_path: Path) -> None:
    server, base, thread = _start_server(tmp_path)
    try:
        with urlopen(base + "/", timeout=3) as response:
            html = response.read().decode()
        assert response.status == 200
        assert "Sources & Ingestion" in html
        assert ">Resolve<" in html
        assert ">Observability<" in html
        assert "Runtime diagnostics" in html
        assert "Already ingested. Existing knowledge version retained" in html
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


def test_web_reupload_identical_content_returns_explicit_replay(tmp_path: Path) -> None:
    server, base, thread = _start_server(tmp_path)
    body = b"# Rotation\n\nRestart the edge service after certificate rotation."
    try:
        first = Request(
            base + "/api/ingest?filename=runbook.md&tenant=local",
            data=body,
            method="POST",
        )
        second = Request(
            base + "/api/ingest?filename=runbook.md&tenant=local",
            data=body,
            method="POST",
        )

        _, first_payload = _read_json(first)
        _, second_payload = _read_json(second)

        assert first_payload["outcome"] == "VERSION_CREATED"
        assert first_payload["replayed"] is False
        assert second_payload["outcome"] == "VERSION_CREATED"
        assert second_payload["replayed"] is True
        assert second_payload["status"] == "available"
        assert second_payload["run_id"] == first_payload["run_id"]
        assert second_payload["chunks_written"] == first_payload["chunks_written"]
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


def test_web_errors_have_structured_operation_envelope(tmp_path: Path) -> None:
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
            payload = json.loads(exc.read())
            assert exc.code == 422
            assert payload["error"]["code"] == "INGESTION_FAILED"
            assert payload["error"]["stage"] == "ingestion"
            assert payload["error"]["retryable"] is False
        else:
            raise AssertionError("unsupported file must be rejected")
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


def test_observability_lists_recent_traces_and_summary(tmp_path: Path) -> None:
    trace_path = tmp_path / "traces.jsonl"
    trace_path.write_text(
        json.dumps(
            {
                "trace_id": "trace_demo",
                "request_id": "request_demo",
                "recorded_at": "2026-10-12T03:00:00+00:00",
                "outcome": "ANSWERED",
                "spans": [
                    {
                        "name": "resolve.retrieval",
                        "status": "OK",
                        "attributes": {
                            "strategy_version": "sqlite-fts5-bm25-v1",
                            "result_count": 1,
                        },
                    },
                    {
                        "name": "resolve.retrieval_gate",
                        "status": "OK",
                        "attributes": {"reason": "passed"},
                    },
                    {
                        "name": "resolve.sufficiency",
                        "status": "OK",
                        "attributes": {
                            "label": "SUFFICIENT",
                            "validation_status": "UNVALIDATED",
                            "model": "test-model",
                            "latency_ms": 100.0,
                            "input_tokens": 20,
                            "output_tokens": 5,
                        },
                    },
                    {
                        "name": "resolve.generation",
                        "status": "OK",
                        "attributes": {
                            "model": "test-model",
                            "latency_ms": 200.0,
                            "input_tokens": 30,
                            "output_tokens": 10,
                        },
                    },
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
        with urlopen(f"http://{host}:{port}/api/observability", timeout=3) as response:
            parsed = json.loads(response.read())

        assert response.status == 200
        assert parsed["summary"]["trace_count"] == 1
        assert parsed["summary"]["answered"] == 1
        assert parsed["summary"]["input_tokens"] == 50
        assert parsed["summary"]["output_tokens"] == 15
        assert parsed["summary"]["average_model_latency_ms"] == 300.0
        assert parsed["summary"]["cost"] is None
        assert parsed["traces"][0]["retrieval_strategy"] == "sqlite-fts5-bm25-v1"
        assert parsed["traces"][0]["sufficiency"] == "SUFFICIENT"
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


def test_runtime_diagnostics_identify_loaded_processing_and_storage(tmp_path: Path) -> None:
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
        ingest = Request(
            f"http://{host}:{port}/api/ingest?filename=runbook.md&tenant=local",
            data=b"# Rotation\n\nRestart the edge service after certificate rotation.",
            method="POST",
        )
        _read_json(ingest)

        with urlopen(f"http://{host}:{port}/api/runtime-diagnostics", timeout=3) as response:
            parsed = json.loads(response.read())

        assert response.status == 200
        assert parsed["ingestion"]["parser_strategy"] == (
            "deterministic-parser-v2-embedded-html-data"
        )
        assert parsed["ingestion"]["processing_version"] == (
            "ingestion-pipeline-v2-embedded-html-data"
        )
        assert parsed["ingestion"]["chunking_strategy"] == "structural-character-v1"
        assert parsed["ingestion"]["chunk_max_characters"] == 1200
        assert parsed["retrieval"]["strategy"] == "sqlite-fts5-bm25-v1"
        assert parsed["storage"]["path"] == str(database.resolve())
        assert parsed["storage"]["knowledge_count"] == 1
        assert parsed["storage"]["current_chunk_count"] >= 1
        assert parsed["model"]["provider"]
        assert parsed["model"]["model"]
        serialized = json.dumps(parsed).casefold()
        assert "api_key" not in serialized
        assert "authorization" not in serialized
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()
