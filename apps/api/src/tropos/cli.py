"""Tropos command-line entrypoint for operational local workflows."""

from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

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
from tropos.core.application.ports.llm import TextCompletionRequest
from tropos.core.domain.access import AccessPolicy, AccessScope
from tropos.core.runtime_config import load_llm_runtime_settings


def _default_knowledge_id(source_namespace: str, source_record_id: str) -> str:
    identity = f"{source_namespace}\0{source_record_id}".encode()
    return f"knowledge_{sha256(identity).hexdigest()}"


def ingest_local_file(
    *,
    file_path: Path,
    database_path: Path,
    tenant_id: str,
    groups: tuple[str, ...] = (),
    knowledge_id: str | None = None,
) -> IngestionResult:
    """Ingest one supported local file through the canonical Tropos pipeline."""

    source_file = file_path.expanduser().resolve()
    if not source_file.is_file():
        raise ValueError(f"file not found: {source_file}")

    database = database_path.expanduser().resolve()
    database.parent.mkdir(parents=True, exist_ok=True)

    normalized_groups = tuple(sorted({group.strip() for group in groups if group.strip()}))
    access_policy = AccessPolicy(
        tenant_id=tenant_id,
        scope=AccessScope.RESTRICTED if normalized_groups else AccessScope.TENANT,
        allowed_groups=normalized_groups,
    )

    source_namespace = "local-file"
    connector = LocalFileSourceConnector(
        root=source_file.parent,
        source_namespace=source_namespace,
        access_policy=access_policy,
    )

    store = SQLiteIngestionStore(database)
    ingestion = IngestKnowledge(
        parser=DeterministicKnowledgeParser(),
        normalizer=DeterministicKnowledgeNormalizer(),
        chunker=DeterministicKnowledgeChunker(),
        source_captures=store,
        knowledge_repository=store,
        runs=store,
    )

    resolved_knowledge_id = (
        knowledge_id.strip()
        if knowledge_id is not None
        else _default_knowledge_id(source_namespace, source_file.name)
    )
    if not resolved_knowledge_id:
        raise ValueError("knowledge_id must not be blank")

    result = IngestFromSource(connector=connector, ingestion=ingestion).execute(
        IngestFromSourceCommand(
            knowledge_id=resolved_knowledge_id,
            source_record_id=source_file.name,
        )
    )

    # Ensure the lexical projection exists and is rebuilt when first introduced.
    # Future writes are maintained by the retriever's SQLite triggers.
    SQLiteFtsKnowledgeRetriever(database)
    return result


def _result_payload(result: IngestionResult, database: Path) -> dict[str, object]:
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
        "database": str(database.expanduser().resolve()),
        "lexical_index": "sqlite-fts5-bm25-v1",
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tropos",
        description="Tropos governed knowledge runtime",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser(
        "ingest",
        help="Ingest one TXT, Markdown, HTML, or DOCX file into governed local knowledge",
    )
    ingest.add_argument("file", type=Path)
    ingest.add_argument(
        "--database",
        type=Path,
        default=Path(".tropos/tropos.db"),
        help="SQLite runtime database (default: .tropos/tropos.db)",
    )
    ingest.add_argument("--tenant", default="local", help="Tenant identifier (default: local)")
    ingest.add_argument(
        "--group",
        action="append",
        default=[],
        help="Restrict knowledge to an access group; repeat for multiple groups",
    )
    ingest.add_argument(
        "--knowledge-id",
        help="Stable Tropos knowledge ID; generated from local source identity when omitted",
    )

    models = commands.add_parser("models", help="Inspect and test configured model runtime")
    model_commands = models.add_subparsers(dest="models_command", required=True)
    model_commands.add_parser(
        "test",
        help="Call the configured primary bootstrap model without printing credentials",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    arguments = parser.parse_args()

    try:
        if arguments.command == "ingest":
            result = ingest_local_file(
                file_path=arguments.file,
                database_path=arguments.database,
                tenant_id=arguments.tenant,
                groups=tuple(arguments.group),
                knowledge_id=arguments.knowledge_id,
            )
            print(json.dumps(_result_payload(result, arguments.database), indent=2))
            return 3 if result.outcome is IngestionOutcome.REBASELINE_REQUIRED else 0

        if arguments.command == "models" and arguments.models_command == "test":
            settings = load_llm_runtime_settings()
            model = build_default_groq_llm(settings)
            result = model.complete_text(
                TextCompletionRequest(
                    system_prompt="You are a connectivity probe. Reply only with OK.",
                    user_prompt="Tropos model connection health check.",
                    prompt_version="model-connection-health-v1",
                    max_output_tokens=16,
                )
            )
            metadata = result.metadata
            print(
                json.dumps(
                    {
                        "status": "healthy",
                        "provider": metadata.provider_id,
                        "connection_id": metadata.connection_id,
                        "deployment_id": metadata.deployment_id,
                        "model": metadata.model_identifier,
                        "latency_ms": round(metadata.latency_ms, 2),
                        "input_tokens": metadata.input_tokens,
                        "output_tokens": metadata.output_tokens,
                        "finish_reason": metadata.finish_reason,
                    },
                    indent=2,
                )
            )
            return 0
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(2, f"Tropos command failed: {exc}\n")

    parser.error("unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
