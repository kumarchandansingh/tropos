from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from tropos.core.adapters.retrieval.sqlite_fts import SQLiteFtsKnowledgeRetriever
from tropos.core.application.retrieval.models import (
    KnowledgeSearchRequest,
    RetrievalAccessContext,
)
from tropos.web import create_app


def _client(tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(
            database_path=tmp_path / "tropos.db",
            trace_path=tmp_path / "traces.jsonl",
        )
    )


def test_web_shell_exposes_sources_and_resolve_workspaces(tmp_path: Path) -> None:
    response = _client(tmp_path).get("/")

    assert response.status_code == 200
    assert "Sources &amp; Ingestion" not in response.text
    assert "Sources & Ingestion" in response.text
    assert ">Resolve<" in response.text
    assert "Sufficiency remains visibly unvalidated" in response.text


def test_web_ingest_creates_searchable_governed_knowledge(tmp_path: Path) -> None:
    database = tmp_path / "tropos.db"
    client = TestClient(
        create_app(
            database_path=database,
            trace_path=tmp_path / "traces.jsonl",
        )
    )

    response = client.post(
        "/api/ingest",
        params={"filename": "runbook.md", "tenant": "tenant-a"},
        content=b"# Rotation\n\nRestart the edge service after certificate rotation.",
        headers={"Content-Type": "text/markdown"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "available"
    assert payload["outcome"] == "VERSION_CREATED"
    assert payload["chunks_written"] > 0

    results = SQLiteFtsKnowledgeRetriever(database).search(
        KnowledgeSearchRequest(
            query="certificate rotation",
            access=RetrievalAccessContext(tenant_id="tenant-a"),
        )
    )
    assert results
    assert results[0].chunk.source_record_id == "runbook.md"


def test_web_ingest_rejects_unsafe_or_unsupported_filename(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.post(
        "/api/ingest",
        params={"filename": "../secret.exe"},
        content=b"not allowed",
    )

    assert response.status_code == 400


def test_web_trace_detail_reads_exact_trace_without_raw_evidence(tmp_path: Path) -> None:
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
    client = TestClient(
        create_app(
            database_path=tmp_path / "tropos.db",
            trace_path=trace_path,
        )
    )

    response = client.get("/api/traces/trace_demo")

    assert response.status_code == 200
    assert response.json()["outcome"] == "ANSWERED"
    assert response.json()["spans"][0]["name"] == "resolve.retrieval"
