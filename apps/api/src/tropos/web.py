"""Local Tropos web application exposing the first product vertical slice."""

from __future__ import annotations

import json
from hashlib import sha256
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from tropos.capabilities.resolve.application.evaluate_evidence_sufficiency import (
    LLMEvidenceSufficiencyJudge,
)
from tropos.capabilities.resolve.application.generate_grounded_answer import (
    LLMGroundedAnswerGenerator,
)
from tropos.capabilities.resolve.application.resolve_question import ResolveQuestion
from tropos.capabilities.resolve.domain.runtime import ResolveOutcome, ResolveResult, RuntimeRequest
from tropos.core.adapters.chunking.deterministic import DeterministicKnowledgeChunker
from tropos.core.adapters.llm.groq import build_default_groq_llm
from tropos.core.adapters.normalization.deterministic import DeterministicKnowledgeNormalizer
from tropos.core.adapters.parsing.deterministic import DeterministicKnowledgeParser
from tropos.core.adapters.persistence.sqlite import SQLiteIngestionStore
from tropos.core.adapters.retrieval.sqlite_fts import SQLiteFtsKnowledgeRetriever
from tropos.core.adapters.sources.local_file import LocalFileSourceConnector
from tropos.core.application.ingestion.ingest_from_source import (
    IngestFromSource,
    IngestFromSourceCommand,
)
from tropos.core.application.ingestion.ingest_knowledge import IngestKnowledge
from tropos.core.application.ingestion.run_state import IngestionOutcome, IngestionResult
from tropos.core.application.observability.trace import JsonlTraceSink
from tropos.core.application.retrieval.models import RetrievalAccessContext
from tropos.core.domain.access import AccessPolicy, AccessScope
from tropos.core.runtime_config import load_llm_runtime_settings
from tropos.web_ui import TROPOS_WEB_HTML

_SUPPORTED_SUFFIXES = {".txt", ".md", ".markdown", ".html", ".htm", ".xhtml", ".docx"}
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _default_knowledge_id(source_namespace: str, source_record_id: str) -> str:
    identity = f"{source_namespace}\0{source_record_id}".encode()
    return f"knowledge_{sha256(identity).hexdigest()}"


def _normalize_groups(groups: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({group.strip() for group in groups if group.strip()}))


def _ingest_file(
    *,
    file_path: Path,
    database_path: Path,
    tenant_id: str,
    groups: tuple[str, ...],
) -> IngestionResult:
    access_policy = AccessPolicy(
        tenant_id=tenant_id,
        scope=AccessScope.RESTRICTED if groups else AccessScope.TENANT,
        allowed_groups=groups,
    )
    source_namespace = "local-file"
    connector = LocalFileSourceConnector(
        root=file_path.parent,
        source_namespace=source_namespace,
        access_policy=access_policy,
    )
    store = SQLiteIngestionStore(database_path)
    ingestion = IngestKnowledge(
        parser=DeterministicKnowledgeParser(),
        normalizer=DeterministicKnowledgeNormalizer(),
        chunker=DeterministicKnowledgeChunker(),
        source_captures=store,
        knowledge_repository=store,
        runs=store,
    )
    result = IngestFromSource(connector=connector, ingestion=ingestion).execute(
        IngestFromSourceCommand(
            knowledge_id=_default_knowledge_id(source_namespace, file_path.name),
            source_record_id=file_path.name,
        )
    )
    SQLiteFtsKnowledgeRetriever(database_path)
    return result


def _ingestion_payload(result: IngestionResult, filename: str) -> dict[str, object]:
    user_status = {
        IngestionOutcome.VERSION_CREATED: "available",
        IngestionOutcome.NO_CHANGE: "available_no_content_change",
        IngestionOutcome.GOVERNANCE_REFRESHED: "available_governance_updated",
        IngestionOutcome.REBASELINE_REQUIRED: "action_required_rebaseline",
    }[result.outcome]
    return {
        "filename": filename,
        "status": user_status,
        "run_id": result.run_id,
        "knowledge_id": result.knowledge_id,
        "outcome": result.outcome.value,
        "reason": result.reason.value,
        "chunks_written": result.chunks_written,
        "governance_refreshed": result.governance_refreshed,
        "replayed": result.replayed,
        "lexical_index": "sqlite-fts5-bm25-v1",
    }


def _resolve_payload(result: ResolveResult) -> dict[str, object]:
    payload: dict[str, object] = {
        "trace_id": result.trace_id,
        "outcome": result.outcome.value,
    }
    if result.evidence_set is not None:
        payload["evidence"] = [
            {
                "alias": item.alias,
                "title": item.reference.source_record_id,
                "source_version": item.reference.source_version,
                "locator": item.reference.locator,
                "rank": item.retrieval_rank,
                "score": item.retrieval_score,
            }
            for item in result.evidence_set.items
        ]
    if result.sufficiency is not None:
        payload["evidence_assessment"] = {
            "label": result.sufficiency.label.value,
            "failure_type": result.sufficiency.failure_type.value,
            "validation_status": result.sufficiency.validation_status.value,
            "missing_facts": list(result.sufficiency.missing_facts),
            "contradictions": list(result.sufficiency.contradictions),
            "rationale": result.sufficiency.rationale,
        }
    if result.outcome is ResolveOutcome.ANSWERED and result.answer is not None:
        payload["answer"] = result.answer.text
        payload["citations"] = [
            {
                "alias": alias,
                "chunk_id": citation.chunk_id,
                "knowledge_id": citation.knowledge_id,
                "locator": citation.locator,
            }
            for alias, citation in zip(
                result.answer.citation_aliases,
                result.answer.citations,
                strict=True,
            )
        ]
    else:
        payload["abstention_reason"] = result.abstention_reason
    return payload


def _read_trace(path: Path, trace_id: str) -> dict[str, object] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        for line in reversed(handle.readlines()):
            try:
                trace = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(trace, dict) and trace.get("trace_id") == trace_id:
                return trace
    return None


def _build_runtime(database: Path, trace_file: Path) -> ResolveQuestion:
    settings = load_llm_runtime_settings()
    model = build_default_groq_llm(settings)
    return ResolveQuestion(
        retriever=SQLiteFtsKnowledgeRetriever(database),
        sufficiency_judge=LLMEvidenceSufficiencyJudge(model),
        answer_generator=LLMGroundedAnswerGenerator(model),
        trace_sink=JsonlTraceSink(trace_file),
    )


def _safe_upload_name(filename: str) -> str:
    safe_name = Path(filename).name
    if safe_name != filename or not safe_name:
        raise ValueError("Unsupported or unsafe file name.")
    if Path(safe_name).suffix.lower() not in _SUPPORTED_SUFFIXES:
        raise ValueError("Unsupported or unsafe file name.")
    return safe_name


def _coerce_resolve_request(payload: object) -> tuple[str, str, tuple[str, ...], int, float | None]:
    if not isinstance(payload, dict):
        raise ValueError("Resolve request must be a JSON object.")
    query = payload.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must not be blank")
    tenant_id = payload.get("tenant_id", "local")
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError("tenant_id must not be blank")
    raw_groups = payload.get("groups", [])
    if not isinstance(raw_groups, list) or any(not isinstance(item, str) for item in raw_groups):
        raise ValueError("groups must be a list of strings")
    limit = payload.get("limit", 5)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
        raise ValueError("limit must be between 1 and 20")
    threshold = payload.get("retrieval_threshold")
    if threshold is not None and (
        isinstance(threshold, bool) or not isinstance(threshold, int | float)
    ):
        raise ValueError("retrieval_threshold must be numeric")
    return (
        query.strip(),
        tenant_id.strip(),
        _normalize_groups(raw_groups),
        limit,
        float(threshold) if threshold is not None else None,
    )


def build_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    database_path: Path | None = None,
    trace_path: Path | None = None,
) -> ThreadingHTTPServer:
    database = (database_path or Path(".tropos/tropos.db")).expanduser().resolve()
    trace_file = (trace_path or Path(".tropos/traces.jsonl")).expanduser().resolve()
    database.parent.mkdir(parents=True, exist_ok=True)

    class Handler(BaseHTTPRequestHandler):
        server_version = "TroposLocal/0.1"

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            self.send_response(status.value)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, html: str) -> None:
            body = html.encode("utf-8")
            self.send_response(HTTPStatus.OK.value)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _error(self, status: HTTPStatus, message: str) -> None:
            self._send_json(status, {"detail": message})

        def _body(self) -> bytes:
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                return b""
            try:
                length = int(raw_length)
            except ValueError as exc:
                raise ValueError("Invalid Content-Length.") from exc
            if length < 0 or length > _MAX_UPLOAD_BYTES:
                raise OverflowError("Request body is too large.")
            return self.rfile.read(length)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send_html(TROPOS_WEB_HTML)
                return
            if parsed.path == "/api/health":
                settings = load_llm_runtime_settings()
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "status": "ready",
                        "provider": settings.provider,
                        "model": settings.model,
                        "model_configured": settings.configured,
                        "retrieval": "sqlite-fts5-bm25-v1",
                    },
                )
                return
            if parsed.path.startswith("/api/traces/"):
                trace_id = parsed.path.removeprefix("/api/traces/")
                if not trace_id.startswith("trace_"):
                    self._error(HTTPStatus.BAD_REQUEST, "Invalid trace identifier.")
                    return
                found = _read_trace(trace_file, trace_id)
                if found is None:
                    self._error(HTTPStatus.NOT_FOUND, "Trace not found.")
                    return
                self._send_json(HTTPStatus.OK, found)
                return
            self._error(HTTPStatus.NOT_FOUND, "Not found.")

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            try:
                body = self._body()
            except OverflowError:
                self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Files are limited to 10 MB.")
                return
            except ValueError as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
                return

            if parsed.path == "/api/ingest":
                query = parse_qs(parsed.query)
                filename = query.get("filename", [""])[0]
                tenant = query.get("tenant", ["local"])[0].strip() or "local"
                groups = _normalize_groups(query.get("group", []))
                if not body:
                    self._error(HTTPStatus.BAD_REQUEST, "The uploaded file is empty.")
                    return
                try:
                    safe_name = _safe_upload_name(filename)
                    with TemporaryDirectory(prefix="tropos-upload-") as temporary:
                        staged = Path(temporary) / safe_name
                        staged.write_bytes(body)
                        result = _ingest_file(
                            file_path=staged,
                            database_path=database,
                            tenant_id=tenant,
                            groups=groups,
                        )
                except (ValueError, OSError, RuntimeError) as exc:
                    self._error(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc))
                    return
                self._send_json(HTTPStatus.OK, _ingestion_payload(result, safe_name))
                return

            if parsed.path == "/api/resolve":
                try:
                    decoded = json.loads(body)
                    resolve_query, tenant, groups, limit, threshold = _coerce_resolve_request(decoded)
                    runtime = _build_runtime(database, trace_file)
                    resolved = runtime.execute(
                        RuntimeRequest(
                            request_id=f"request_{uuid4().hex}",
                            query=resolve_query,
                            access=RetrievalAccessContext(tenant_id=tenant, groups=groups),
                            retrieval_limit=limit,
                            retrieval_threshold=threshold,
                        )
                    )
                except json.JSONDecodeError:
                    self._error(HTTPStatus.BAD_REQUEST, "Request body must be valid JSON.")
                    return
                except ValueError as exc:
                    self._error(HTTPStatus.BAD_REQUEST, str(exc))
                    return
                except (OSError, RuntimeError) as exc:
                    self._error(HTTPStatus.BAD_GATEWAY, str(exc))
                    return
                self._send_json(HTTPStatus.OK, _resolve_payload(resolved))
                return

            self._error(HTTPStatus.NOT_FOUND, "Not found.")

    return ThreadingHTTPServer((host, port), Handler)


def serve(*, host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the local Tropos web application."""

    server = build_server(host=host, port=port)
    print(f"Tropos web UI: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
