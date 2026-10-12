"""Local Tropos web application exposing the first product vertical slice."""

from __future__ import annotations

import inspect
import json
import sqlite3
import subprocess
import sys
from hashlib import sha256
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast
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
from tropos.core.retrieval_runtime import (
    build_runtime_retrieval,
    materialize_runtime_embeddings,
)
from tropos.core.runtime_config import (
    RetrievalStrategy,
    load_embedding_runtime_settings,
    load_llm_runtime_settings,
)
from tropos.web_ui import TROPOS_WEB_HTML

_SUPPORTED_SUFFIXES = {".txt", ".md", ".markdown", ".html", ".htm", ".xhtml", ".docx"}
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _repository_root() -> Path | None:
    current = Path(__file__).resolve()
    for candidate in (current.parent, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _git_value(repository: Path | None, *arguments: str) -> str | None:
    if repository is None:
        return None
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=False,
            capture_output=True,
            text=True,
            timeout=1.0,
        )
    except OSError, subprocess.SubprocessError:
        return None
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value or None


def _database_diagnostics(
    database: Path,
    *,
    embedding_strategy_version: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "path": str(database),
        "exists": database.exists(),
        "size_bytes": database.stat().st_size if database.exists() else 0,
        "knowledge_count": 0,
        "chunk_count": 0,
        "current_chunk_count": 0,
        "embedding_count": 0,
        "missing_embedding_count": 0,
        "latest_processing_version": None,
        "error": None,
    }
    if not database.exists():
        return payload

    try:
        with sqlite3.connect(database) as connection:
            payload["knowledge_count"] = int(
                connection.execute("SELECT COUNT(*) FROM knowledge_state").fetchone()[0]
            )
            payload["chunk_count"] = int(
                connection.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()[0]
            )
            payload["current_chunk_count"] = int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM knowledge_chunks AS c
                    JOIN knowledge_state AS s
                      ON s.knowledge_id = c.knowledge_id
                    WHERE s.lifecycle_status = 'ACTIVE'
                      AND c.normalized_content_fingerprint = s.content_fingerprint
                      AND c.normalization_strategy_version = s.normalization_strategy_version
                    """
                ).fetchone()[0]
            )
            row = connection.execute(
                """
                SELECT processing_version
                FROM ingestion_runs
                ORDER BY started_at DESC
                LIMIT 1
                """
            ).fetchone()
            payload["latest_processing_version"] = str(row[0]) if row else None

            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if embedding_strategy_version is not None:
                if "knowledge_embeddings" in tables:
                    payload["embedding_count"] = int(
                        connection.execute(
                            """
                            SELECT COUNT(*)
                            FROM knowledge_embeddings
                            WHERE embedding_strategy_version = ?
                            """,
                            (embedding_strategy_version,),
                        ).fetchone()[0]
                    )
                    payload["missing_embedding_count"] = int(
                        connection.execute(
                            """
                            SELECT COUNT(*)
                            FROM knowledge_chunks AS c
                            JOIN knowledge_state AS s
                              ON s.knowledge_id = c.knowledge_id
                            LEFT JOIN knowledge_embeddings AS e
                              ON e.chunk_id = c.chunk_id
                             AND e.embedding_strategy_version = ?
                            WHERE s.lifecycle_status = 'ACTIVE'
                              AND c.normalized_content_fingerprint = s.content_fingerprint
                              AND c.normalization_strategy_version = s.normalization_strategy_version
                              AND e.chunk_id IS NULL
                            """,
                            (embedding_strategy_version,),
                        ).fetchone()[0]
                    )
                else:
                    payload["missing_embedding_count"] = payload["current_chunk_count"]
    except (sqlite3.DatabaseError, OSError) as exc:
        payload["error"] = f"{type(exc).__name__}: {exc}"
    return payload


def _runtime_diagnostics(database: Path) -> dict[str, object]:
    repository = _repository_root()
    chunker = DeterministicKnowledgeChunker()
    settings = load_llm_runtime_settings()
    embedding_settings = load_embedding_runtime_settings()

    return {
        "build": {
            "git_commit": _git_value(repository, "rev-parse", "--short", "HEAD"),
            "git_branch": _git_value(repository, "rev-parse", "--abbrev-ref", "HEAD"),
            "repository_root": str(repository) if repository is not None else None,
        },
        "python": {
            "version": sys.version.split()[0],
            "executable": sys.executable,
            "working_directory": str(Path.cwd()),
            "web_module": str(Path(__file__).resolve()),
            "parser_module": str(Path(inspect.getfile(DeterministicKnowledgeParser)).resolve()),
        },
        "ingestion": {
            "parser_strategy": DeterministicKnowledgeParser.strategy_version,
            "processing_version": IngestKnowledge.default_processing_version,
            "chunking_strategy": chunker.strategy_version,
            "chunk_max_characters": chunker.max_characters,
        },
        "storage": _database_diagnostics(
            database,
            embedding_strategy_version=(
                f"openai:{embedding_settings.model}:{embedding_settings.dimensions}:v1"
                if embedding_settings.provider == "openai"
                else None
            ),
        ),
        "retrieval": {
            "default_strategy": RetrievalStrategy.BM25.value,
            "bm25_strategy": SQLiteFtsKnowledgeRetriever.strategy_version_name,
            "available_strategies": tuple(strategy.value for strategy in RetrievalStrategy),
            "embedding_provider": embedding_settings.provider,
            "embedding_model": embedding_settings.model,
            "embedding_dimensions": embedding_settings.dimensions,
            "embedding_configured": embedding_settings.configured,
        },
        "model": {
            "provider": settings.provider,
            "model": settings.model,
            "configured": settings.configured,
        },
    }


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
                "strategy": item.retrieval_strategy_version,
                "components": [
                    {
                        "strategy": component.strategy_version,
                        "rank": component.rank,
                        "score": component.score,
                    }
                    for component in item.retrieval_score_components
                ],
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


def _read_traces(path: Path, *, limit: int = 100) -> list[dict[str, object]]:
    if not path.exists():
        return []
    traces: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in reversed(handle.readlines()):
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                traces.append(cast(dict[str, object], parsed))
            if len(traces) >= limit:
                break
    return traces


def _read_trace(path: Path, trace_id: str) -> dict[str, object] | None:
    return next((trace for trace in _read_traces(path) if trace.get("trace_id") == trace_id), None)


def _span_by_name(trace: dict[str, object], name: str) -> dict[str, object] | None:
    spans = trace.get("spans")
    if not isinstance(spans, list):
        return None
    for raw in spans:
        if isinstance(raw, dict) and raw.get("name") == name:
            return cast(dict[str, object], raw)
    return None


def _span_attributes(span: dict[str, object] | None) -> dict[str, object]:
    if span is None:
        return {}
    attributes = span.get("attributes")
    return cast(dict[str, object], attributes) if isinstance(attributes, dict) else {}


def _trace_summary(trace: dict[str, object]) -> dict[str, object]:
    retrieval = _span_attributes(_span_by_name(trace, "resolve.retrieval"))
    gate_span = _span_by_name(trace, "resolve.retrieval_gate")
    gate = _span_attributes(gate_span)
    sufficiency = _span_attributes(_span_by_name(trace, "resolve.sufficiency"))
    generation = _span_attributes(_span_by_name(trace, "resolve.generation"))
    model = generation.get("model") or sufficiency.get("model")
    latency_values = [
        value
        for value in (sufficiency.get("latency_ms"), generation.get("latency_ms"))
        if isinstance(value, int | float)
    ]
    input_values = [
        value
        for value in (sufficiency.get("input_tokens"), generation.get("input_tokens"))
        if isinstance(value, int)
    ]
    output_values = [
        value
        for value in (sufficiency.get("output_tokens"), generation.get("output_tokens"))
        if isinstance(value, int)
    ]
    return {
        "trace_id": trace.get("trace_id"),
        "request_id": trace.get("request_id"),
        "outcome": trace.get("outcome"),
        "recorded_at": trace.get("recorded_at"),
        "retrieval_strategy": retrieval.get("strategy_version"),
        "retrieval_latency_ms": retrieval.get("latency_ms"),
        "result_count": retrieval.get("result_count"),
        "gate_status": gate_span.get("status") if gate_span else None,
        "gate_reason": gate.get("reason"),
        "sufficiency": sufficiency.get("label"),
        "validation_status": sufficiency.get("validation_status"),
        "model": model,
        "model_latency_ms": round(sum(float(value) for value in latency_values), 2)
        if latency_values
        else None,
        "input_tokens": sum(input_values),
        "output_tokens": sum(output_values),
    }


def _observability_payload(path: Path) -> dict[str, object]:
    traces = _read_traces(path, limit=200)
    summaries = [_trace_summary(trace) for trace in traces]
    answered = sum(summary.get("outcome") == "ANSWERED" for summary in summaries)
    abstained = sum(
        summary.get("outcome") in {"RETRIEVAL_ABSTAINED", "EVIDENCE_INSUFFICIENT"}
        for summary in summaries
    )
    failed = sum(summary.get("outcome") == "RUNTIME_FAILED" for summary in summaries)
    input_tokens = 0
    output_tokens = 0
    latency_values: list[float] = []
    for summary in summaries:
        input_value = summary.get("input_tokens")
        output_value = summary.get("output_tokens")
        latency_value = summary.get("model_latency_ms")
        if isinstance(input_value, int):
            input_tokens += input_value
        if isinstance(output_value, int):
            output_tokens += output_value
        if isinstance(latency_value, int | float):
            latency_values.append(float(latency_value))
    return {
        "summary": {
            "trace_count": len(summaries),
            "answered": answered,
            "abstained": abstained,
            "failed": failed,
            "answer_rate": round(answered / len(summaries), 3) if summaries else None,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "average_model_latency_ms": round(sum(latency_values) / len(latency_values), 2)
            if latency_values
            else None,
            "cost": None,
        },
        "traces": summaries,
    }


def _build_runtime(
    database: Path,
    trace_file: Path,
    *,
    retrieval_strategy: RetrievalStrategy,
) -> ResolveQuestion:
    retrieval = build_runtime_retrieval(
        database_path=database,
        strategy=retrieval_strategy,
        embedding_settings=load_embedding_runtime_settings(),
        materialize_missing=False,
    )
    settings = load_llm_runtime_settings()
    model = build_default_groq_llm(settings)
    return ResolveQuestion(
        retriever=retrieval.retriever,
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


def _coerce_resolve_request(
    payload: object,
) -> tuple[str, str, tuple[str, ...], int, float | None, RetrievalStrategy]:
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
    raw_strategy = payload.get("retrieval_strategy", RetrievalStrategy.BM25.value)
    if not isinstance(raw_strategy, str):
        raise ValueError("retrieval_strategy must be a string")
    try:
        retrieval_strategy = RetrievalStrategy(raw_strategy)
    except ValueError as exc:
        allowed = ", ".join(strategy.value for strategy in RetrievalStrategy)
        raise ValueError(f"retrieval_strategy must be one of: {allowed}") from exc
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
        retrieval_strategy,
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

        def _error(
            self,
            status: HTTPStatus,
            message: str,
            *,
            code: str = "REQUEST_FAILED",
            stage: str = "request",
            retryable: bool = False,
        ) -> None:
            self._send_json(
                status,
                {
                    "detail": message,
                    "error": {
                        "code": code,
                        "stage": stage,
                        "message": message,
                        "retryable": retryable,
                    },
                },
            )

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
                        "retrieval_strategies": [
                            strategy.value for strategy in RetrievalStrategy
                        ],
                        "embedding_configured": load_embedding_runtime_settings().configured,
                    },
                )
                return
            if parsed.path == "/api/observability":
                self._send_json(HTTPStatus.OK, _observability_payload(trace_file))
                return
            if parsed.path == "/api/runtime-diagnostics":
                self._send_json(HTTPStatus.OK, _runtime_diagnostics(database))
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
                self._error(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    "Files are limited to 10 MB.",
                    code="UPLOAD_TOO_LARGE",
                    stage="upload",
                )
                return
            except ValueError as exc:
                self._error(
                    HTTPStatus.BAD_REQUEST,
                    str(exc),
                    code="INVALID_REQUEST",
                    stage="request",
                )
                return

            if parsed.path == "/api/embeddings/materialize":
                try:
                    materialized = materialize_runtime_embeddings(
                        database_path=database,
                        settings=load_embedding_runtime_settings(),
                    )
                except (ValueError, OSError, RuntimeError) as exc:
                    self._error(
                        HTTPStatus.BAD_GATEWAY,
                        str(exc),
                        code="EMBEDDING_RUNTIME_FAILED",
                        stage="embeddings",
                        retryable=True,
                    )
                    return
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "embedded_count": materialized.embedded_count,
                        "strategy_version": materialized.strategy_version,
                        "model": materialized.model_identifier,
                    },
                )
                return

            if parsed.path == "/api/ingest":
                query = parse_qs(parsed.query)
                filename = query.get("filename", [""])[0]
                tenant = query.get("tenant", ["local"])[0].strip() or "local"
                groups = _normalize_groups(query.get("group", []))
                if not body:
                    self._error(
                        HTTPStatus.BAD_REQUEST,
                        "The uploaded file is empty.",
                        code="EMPTY_UPLOAD",
                        stage="upload",
                    )
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
                    self._error(
                        HTTPStatus.UNPROCESSABLE_ENTITY,
                        str(exc),
                        code="INGESTION_FAILED",
                        stage="ingestion",
                        retryable=isinstance(exc, OSError | RuntimeError),
                    )
                    return
                self._send_json(HTTPStatus.OK, _ingestion_payload(result, safe_name))
                return

            if parsed.path == "/api/resolve":
                try:
                    decoded = json.loads(body)
                    (
                        resolve_query,
                        tenant,
                        groups,
                        limit,
                        threshold,
                        retrieval_strategy,
                    ) = _coerce_resolve_request(decoded)
                    runtime = _build_runtime(
                        database,
                        trace_file,
                        retrieval_strategy=retrieval_strategy,
                    )
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
                    self._error(
                        HTTPStatus.BAD_REQUEST,
                        "Request body must be valid JSON.",
                        code="INVALID_JSON",
                        stage="resolve",
                    )
                    return
                except ValueError as exc:
                    self._error(
                        HTTPStatus.BAD_REQUEST,
                        str(exc),
                        code="INVALID_RESOLVE_REQUEST",
                        stage="resolve",
                    )
                    return
                except (OSError, RuntimeError) as exc:
                    self._error(
                        HTTPStatus.BAD_GATEWAY,
                        str(exc),
                        code="RUNTIME_DEPENDENCY_FAILED",
                        stage="resolve",
                        retryable=True,
                    )
                    return
                payload = _resolve_payload(resolved)
                payload["retrieval_strategy"] = retrieval_strategy.value
                self._send_json(HTTPStatus.OK, payload)
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
