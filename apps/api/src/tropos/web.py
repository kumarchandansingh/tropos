"""Local Tropos web application exposing the first product vertical slice."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated
from uuid import uuid4

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from tropos.capabilities.resolve.application.evaluate_evidence_sufficiency import (
    LLMEvidenceSufficiencyJudge,
)
from tropos.capabilities.resolve.application.generate_grounded_answer import (
    LLMGroundedAnswerGenerator,
)
from tropos.capabilities.resolve.application.resolve_question import ResolveQuestion
from tropos.capabilities.resolve.domain.runtime import ResolveOutcome, RuntimeRequest
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


class ResolveWebRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8000)
    tenant_id: str = Field(default="local", min_length=1, max_length=200)
    groups: list[str] = Field(default_factory=list)
    limit: int = Field(default=5, ge=1, le=20)
    retrieval_threshold: float | None = None


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


def _ingestion_payload(result: IngestionResult) -> dict[str, object]:
    user_status = {
        IngestionOutcome.VERSION_CREATED: "available",
        IngestionOutcome.NO_CHANGE: "available_no_content_change",
        IngestionOutcome.GOVERNANCE_REFRESHED: "available_governance_updated",
        IngestionOutcome.REBASELINE_REQUIRED: "action_required_rebaseline",
    }[result.outcome]
    return {
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


def _resolve_payload(resolved: object) -> dict[str, object]:
    result = resolved
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


def create_app(
    *,
    database_path: Path | None = None,
    trace_path: Path | None = None,
) -> FastAPI:
    database = (database_path or Path(".tropos/tropos.db")).expanduser().resolve()
    trace_file = (trace_path or Path(".tropos/traces.jsonl")).expanduser().resolve()
    database.parent.mkdir(parents=True, exist_ok=True)

    app = FastAPI(
        title="Tropos",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url=None,
    )

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return TROPOS_WEB_HTML

    @app.get("/api/health")
    def health() -> dict[str, object]:
        settings = load_llm_runtime_settings()
        return {
            "status": "ready",
            "provider": settings.provider,
            "model": settings.model,
            "model_configured": settings.configured,
            "retrieval": "sqlite-fts5-bm25-v1",
        }

    @app.post("/api/ingest")
    async def ingest(
        request: Request,
        filename: Annotated[str, Query(min_length=1, max_length=240)],
        tenant: Annotated[str, Query(min_length=1, max_length=200)] = "local",
        group: Annotated[list[str] | None, Query()] = None,
    ) -> dict[str, object]:
        safe_name = Path(filename).name
        suffix = Path(safe_name).suffix.lower()
        if safe_name != filename or suffix not in _SUPPORTED_SUFFIXES:
            raise HTTPException(status_code=400, detail="Unsupported or unsafe file name.")

        body = await request.body()
        if not body:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")
        if len(body) > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Files are limited to 10 MB in this slice.")

        try:
            with TemporaryDirectory(prefix="tropos-upload-") as temporary:
                staged = Path(temporary) / safe_name
                staged.write_bytes(body)
                result = _ingest_file(
                    file_path=staged,
                    database_path=database,
                    tenant_id=tenant,
                    groups=_normalize_groups(group or []),
                )
        except (ValueError, OSError, RuntimeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        payload = _ingestion_payload(result)
        payload["filename"] = safe_name
        return payload

    @app.post("/api/resolve")
    def resolve(
        body: Annotated[ResolveWebRequest, Body()],
    ) -> dict[str, object]:
        settings = load_llm_runtime_settings()
        try:
            model = build_default_groq_llm(settings)
            runtime = ResolveQuestion(
                retriever=SQLiteFtsKnowledgeRetriever(database),
                sufficiency_judge=LLMEvidenceSufficiencyJudge(model),
                answer_generator=LLMGroundedAnswerGenerator(model),
                trace_sink=JsonlTraceSink(trace_file),
            )
            resolved = runtime.execute(
                RuntimeRequest(
                    request_id=f"request_{uuid4().hex}",
                    query=body.query,
                    access=RetrievalAccessContext(
                        tenant_id=body.tenant_id,
                        groups=_normalize_groups(body.groups),
                    ),
                    retrieval_limit=body.limit,
                    retrieval_threshold=body.retrieval_threshold,
                )
            )
        except (ValueError, OSError, RuntimeError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return _resolve_payload(resolved)

    @app.get("/api/traces/{trace_id}")
    def trace(trace_id: str) -> dict[str, object]:
        if not trace_id.startswith("trace_"):
            raise HTTPException(status_code=400, detail="Invalid trace identifier.")
        found = _read_trace(trace_file, trace_id)
        if found is None:
            raise HTTPException(status_code=404, detail="Trace not found.")
        return found

    return app


app = create_app()


def serve(*, host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the local Tropos web application."""

    import uvicorn

    uvicorn.run("tropos.web:app", host=host, port=port, reload=False)
