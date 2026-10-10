"""Run BM25, dense MPNet, and hybrid RRF with pinned real-model provenance."""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict, cast

import sentence_transformers
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
from tropos.evals.catalogue import authorized
from tropos.evals.retrieval import RetrievalEvalCase, RetrievalEvalReport, evaluate_retrieval

_MODEL_IDENTIFIER = "sentence-transformers/all-mpnet-base-v2"
_MODEL_REVISION = "e8c3b32edf5434bc2275fc9bab85f82640a19130"
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
        self._model = SentenceTransformer(
            _MODEL_IDENTIFIER,
            revision=_MODEL_REVISION,
        )

    @property
    def strategy_version(self) -> str:
        return _STRATEGY_VERSION

    @property
    def model_identifier(self) -> str:
        return _MODEL_IDENTIFIER

    @property
    def model_revision(self) -> str:
        return _MODEL_REVISION

    @property
    def dimensions(self) -> int:
        dimensions = self._model.get_embedding_dimension()
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


def _access_gate(
    reports: dict[str, RetrievalEvalReport],
    dataset: _DatasetRow,
) -> tuple[bool, list[dict[str, object]]]:
    """Fail only when a retriever returns evidence the case is not authorized to see."""

    failures: list[dict[str, object]] = []
    boundary_cases = tuple(row for row in dataset["cases"] if "access-boundary" in row["tags"])
    for row in boundary_cases:
        access = RetrievalAccessContext(
            tenant_id=row["tenant_id"],
            groups=tuple(row["groups"]),
        )
        forbidden = {
            document["knowledge_id"]
            for document in dataset["documents"]
            if not authorized(
                AccessPolicy(
                    tenant_id=document["tenant_id"],
                    scope=AccessScope(document["scope"]),
                    allowed_groups=tuple(document["allowed_groups"]),
                ),
                access,
            )
        }
        for strategy, report in reports.items():
            result = next(item for item in report.case_results if item.case_id == row["case_id"])
            leaked = tuple(
                knowledge_id
                for knowledge_id in result.retrieved_knowledge_ids
                if knowledge_id in forbidden
            )
            if leaked:
                failures.append(
                    {
                        "strategy": strategy,
                        "case_id": row["case_id"],
                        "unauthorized_knowledge_ids": leaked,
                    }
                )
    return not failures, failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Pinned real-model hybrid retrieval evaluation")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
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
        gate_passed, gate_failures = _access_gate(reports, dataset)

        output = {
            "schema_version": 1,
            "dataset_id": dataset["dataset_id"],
            "model_identifier": provider.model_identifier,
            "model_revision": provider.model_revision,
            "sentence_transformers_version": sentence_transformers.__version__,
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
            "gate": {
                "policy": "retrieval-access-boundaries-v1",
                "passed": gate_passed,
                "failures": gate_failures,
                "note": (
                    "Authorized-but-irrelevant nearest neighbours are a relevance/abstention "
                    "problem and remain non-blocking until QE-109; unauthorized evidence is a "
                    "hard invariant."
                ),
            },
        }
        serialized = json.dumps(output, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        if arguments.output is None:
            print(serialized, end="")
        else:
            arguments.output.parent.mkdir(parents=True, exist_ok=True)
            arguments.output.write_text(serialized, encoding="utf-8")
        return 0 if gate_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
