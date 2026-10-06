"""Compare BM25, dense MPNet, and hybrid RRF on the unchanged golden V1 corpus."""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict, cast

from sentence_transformers import SentenceTransformer

from tropos.core.adapters.chunking.deterministic import DeterministicKnowledgeChunker
from tropos.core.adapters.embeddings.sqlite import SQLiteEmbeddingRepository
from tropos.core.adapters.normalization.deterministic import DeterministicKnowledgeNormalizer
from tropos.core.adapters.parsing.deterministic import DeterministicKnowledgeParser
from tropos.core.adapters.persistence.sqlite import SQLiteIngestionStore
from tropos.core.adapters.retrieval.exact_vector import ExactVectorKnowledgeRetriever
from tropos.core.adapters.retrieval.hybrid_rrf import HybridRrfKnowledgeRetriever
from tropos.core.adapters.retrieval.sqlite_fts import SQLiteFtsKnowledgeRetriever
from tropos.core.application.embeddings.materialize import MaterializeEmbeddings
from tropos.core.application.embeddings.models import EmbeddingVector, SimilarityMetric
from tropos.core.application.ingestion.ingest_knowledge import (
    IngestKnowledge,
    IngestKnowledgeCommand,
)
from tropos.core.application.ingestion.raw_record import RawKnowledgeRecord
from tropos.core.application.retrieval.models import RetrievalAccessContext
from tropos.core.domain.access import AccessPolicy, AccessScope
from tropos.evals.retrieval import RetrievalEvalCase, evaluate_retrieval

_MODEL_IDENTIFIER = "sentence-transformers/all-mpnet-base-v2"
_STRATEGY_VERSION = "sentence-transformers-all-mpnet-base-v2-normalized-v1"


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


class _SentenceTransformerProvider:
    def __init__(self) -> None:
        self._model = SentenceTransformer(_MODEL_IDENTIFIER)

    @property
    def strategy_version(self) -> str:
        return _STRATEGY_VERSION

    @property
    def model_identifier(self) -> str:
        return _MODEL_IDENTIFIER

    @property
    def dimensions(self) -> int:
        dimensions = self._model.get_sentence_embedding_dimension()
        if dimensions is None:
            raise RuntimeError("sentence-transformer did not report embedding dimensions")
        return int(dimensions)

    @property
    def similarity_metric(self) -> SimilarityMetric:
        return SimilarityMetric.COSINE

    def embed_documents(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]:
        return self._encode(texts)

    def embed_query(self, text: str) -> EmbeddingVector:
        return self._encode((text,))[0]

    def _encode(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]:
        vectors: Any = self._model.encode(
            list(texts),
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return tuple(
            EmbeddingVector(tuple(float(value) for value in row.tolist())) for row in vectors
        )


def _load_dataset() -> _DatasetRow:
    path = Path(__file__).parents[1] / "evals" / "retrieval" / "golden_v1.json"
    return cast(_DatasetRow, json.loads(path.read_text(encoding="utf-8")))


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
    dataset = _load_dataset()

    with tempfile.TemporaryDirectory() as temporary_directory:
        database = Path(temporary_directory) / "tropos.db"
        store = SQLiteIngestionStore(database)
        orchestrator = _orchestrator(store)

        for row in dataset["documents"]:
            raw = RawKnowledgeRecord(
                source_system="eval:golden-v1",
                source_record_id=f"{row['knowledge_id']}.md",
                source_version="1",
                content_type="text/markdown",
                payload=row["text"].encode("utf-8"),
                access_policy=AccessPolicy(
                    tenant_id=row["tenant_id"],
                    scope=AccessScope(row["scope"]),
                    allowed_groups=tuple(row["allowed_groups"]),
                ),
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

        provider = _SentenceTransformerProvider()
        repository = SQLiteEmbeddingRepository(database)
        MaterializeEmbeddings(provider=provider, repository=repository).execute()

        lexical = SQLiteFtsKnowledgeRetriever(database)
        dense = ExactVectorKnowledgeRetriever(provider=provider, repository=repository)
        hybrid = HybridRrfKnowledgeRetriever(lexical=lexical, dense=dense)

        reports = {
            "bm25": evaluate_retrieval(lexical, cases),
            "dense": evaluate_retrieval(dense, cases),
            "hybrid": evaluate_retrieval(hybrid, cases),
        }

        output = {
            "dataset_id": dataset["dataset_id"],
            "model_identifier": provider.model_identifier,
            "reports": {name: report.as_dict() for name, report in reports.items()},
            "case_comparison": [
                {
                    "case_id": case.case_id,
                    "tags": case.tags,
                    **{
                        name: next(
                            result.retrieved_knowledge_ids
                            for result in report.case_results
                            if result.case_id == case.case_id
                        )
                        for name, report in reports.items()
                    },
                }
                for case in cases
            ],
        }
        print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
