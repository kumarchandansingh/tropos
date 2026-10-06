"""Run the golden retrieval corpus against BM25 and a real OpenAI embedding model.

Usage from apps/api:
    OPENAI_API_KEY=... uv run python scripts/evaluate_dense_retrieval.py

The script intentionally stays out of CI because it makes a paid external model call.
Unit tests use fakes only to prove mechanics, governance, lineage, and idempotency.
"""

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict, cast

from tropos.core.adapters.chunking.deterministic import DeterministicKnowledgeChunker
from tropos.core.adapters.embeddings.openai import OpenAIEmbeddingProvider
from tropos.core.adapters.embeddings.sqlite import SQLiteEmbeddingRepository
from tropos.core.adapters.normalization.deterministic import DeterministicKnowledgeNormalizer
from tropos.core.adapters.parsing.deterministic import DeterministicKnowledgeParser
from tropos.core.adapters.persistence.sqlite import SQLiteIngestionStore
from tropos.core.adapters.retrieval.exact_vector import ExactVectorKnowledgeRetriever
from tropos.core.adapters.retrieval.hybrid_rrf import HybridRrfKnowledgeRetriever
from tropos.core.adapters.retrieval.sqlite_fts import SQLiteFtsKnowledgeRetriever
from tropos.core.application.embeddings.materialize import MaterializeEmbeddings
from tropos.core.application.ingestion.ingest_knowledge import (
    IngestKnowledge,
    IngestKnowledgeCommand,
)
from tropos.core.application.ingestion.raw_record import RawKnowledgeRecord
from tropos.core.application.retrieval.models import RetrievalAccessContext
from tropos.core.domain.access import AccessPolicy, AccessScope
from tropos.evals.retrieval import RetrievalEvalCase, evaluate_retrieval


class _DocumentRow(TypedDict):
    knowledge_id: str
    text: str
    tenant_id: str
    scope: str
    allowed_groups: list[str]


class _CaseRow(TypedDict):
    case_id: str
    query: str
    tenant_id: str
    groups: list[str]
    relevant_knowledge_ids: list[str]
    tags: list[str]


class _DatasetRow(TypedDict):
    dataset_id: str
    label_scope: str
    notes: str
    documents: list[_DocumentRow]
    cases: list[_CaseRow]


def _load_dataset() -> _DatasetRow:
    dataset_path = Path(__file__).parents[1] / "evals" / "retrieval" / "golden_v1.json"
    return cast(_DatasetRow, json.loads(dataset_path.read_text(encoding="utf-8")))


def _orchestrator(store: SQLiteIngestionStore) -> IngestKnowledge:
    return IngestKnowledge(
        parser=DeterministicKnowledgeParser(),
        normalizer=DeterministicKnowledgeNormalizer(),
        chunker=DeterministicKnowledgeChunker(max_characters=2000),
        source_captures=store,
        knowledge_repository=store,
        runs=store,
    )


def main() -> None:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required for the real-model evaluation")

    dataset = _load_dataset()
    with tempfile.TemporaryDirectory() as temporary_directory:
        database = Path(temporary_directory) / "tropos.db"
        store = SQLiteIngestionStore(database)
        orchestrator = _orchestrator(store)

        for row in dataset["documents"]:
            access_policy = AccessPolicy(
                tenant_id=row["tenant_id"],
                scope=AccessScope(row["scope"]),
                allowed_groups=tuple(row["allowed_groups"]),
            )
            raw = RawKnowledgeRecord(
                source_system="eval:golden-v1",
                source_record_id=f"{row['knowledge_id']}.md",
                source_version="1",
                content_type="text/markdown",
                payload=row["text"].encode("utf-8"),
                access_policy=access_policy,
                captured_at=datetime(2026, 10, 6, tzinfo=UTC),
            )
            orchestrator.execute(
                IngestKnowledgeCommand(
                    knowledge_id=row["knowledge_id"],
                    raw_record=raw,
                )
            )

        cases = tuple(
            RetrievalEvalCase(
                case_id=row["case_id"],
                query=row["query"],
                access=RetrievalAccessContext(
                    tenant_id=row["tenant_id"],
                    groups=tuple(row["groups"]),
                ),
                relevant_knowledge_ids=tuple(row["relevant_knowledge_ids"]),
                tags=tuple(row["tags"]),
            )
            for row in dataset["cases"]
        )

        provider = OpenAIEmbeddingProvider(api_key=api_key)
        embedding_repository = SQLiteEmbeddingRepository(database)
        materialization = MaterializeEmbeddings(
            provider=provider,
            repository=embedding_repository,
        ).execute()

        lexical_retriever = SQLiteFtsKnowledgeRetriever(database)
        dense_retriever = ExactVectorKnowledgeRetriever(
            provider=provider,
            repository=embedding_repository,
        )
        hybrid_retriever = HybridRrfKnowledgeRetriever(
            lexical=lexical_retriever,
            dense=dense_retriever,
        )

        lexical_report = evaluate_retrieval(lexical_retriever, cases)
        dense_report = evaluate_retrieval(dense_retriever, cases)
        hybrid_report = evaluate_retrieval(hybrid_retriever, cases)

        lexical_by_id = {case.case_id: case for case in lexical_report.case_results}
        dense_by_id = {case.case_id: case for case in dense_report.case_results}
        hybrid_by_id = {case.case_id: case for case in hybrid_report.case_results}

        comparison = {
            "dataset_id": dataset["dataset_id"],
            "materialization": {
                "embedded_count": materialization.embedded_count,
                "strategy_version": materialization.strategy_version,
                "model_identifier": materialization.model_identifier,
            },
            "bm25": lexical_report.as_dict(),
            "dense": dense_report.as_dict(),
            "hybrid": hybrid_report.as_dict(),
            "case_comparison": [
                {
                    "case_id": case.case_id,
                    "tags": case.tags,
                    "bm25": lexical_by_id[case.case_id].retrieved_knowledge_ids,
                    "dense": dense_by_id[case.case_id].retrieved_knowledge_ids,
                    "hybrid": hybrid_by_id[case.case_id].retrieved_knowledge_ids,
                }
                for case in cases
            ],
        }
        print(json.dumps(comparison, indent=2))


if __name__ == "__main__":
    main()
