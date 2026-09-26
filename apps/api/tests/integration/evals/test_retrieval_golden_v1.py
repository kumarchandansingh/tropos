import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict, cast

import pytest

from tropos.core.adapters.chunking.deterministic import DeterministicKnowledgeChunker
from tropos.core.adapters.normalization.deterministic import DeterministicKnowledgeNormalizer
from tropos.core.adapters.parsing.deterministic import DeterministicKnowledgeParser
from tropos.core.adapters.persistence.sqlite import SQLiteIngestionStore
from tropos.core.adapters.retrieval.sqlite_fts import SQLiteFtsKnowledgeRetriever
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
    dataset_path = Path(__file__).parents[3] / "evals" / "retrieval" / "golden_v1.json"
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


def test_golden_v1_establishes_measured_lexical_retrieval_baseline(tmp_path: Path) -> None:
    dataset = _load_dataset()
    assert dataset["dataset_id"] == "tropos-retrieval-golden-v1"
    assert dataset["label_scope"] == "knowledge_id"

    database = tmp_path / "tropos.db"
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
            captured_at=datetime(2026, 9, 26, tzinfo=UTC),
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

    report = evaluate_retrieval(SQLiteFtsKnowledgeRetriever(database), cases)

    assert report.strategy_version == "sqlite-fts5-bm25-v1"
    assert report.case_count == 14
    assert report.answerable_case_count == 10
    assert report.no_answer_case_count == 4
    assert report.recall_at_1 == pytest.approx(0.8)
    assert report.recall_at_3 == pytest.approx(0.8)
    assert report.recall_at_5 == pytest.approx(0.8)
    assert report.precision_at_5 == pytest.approx(0.16)
    assert report.mrr == pytest.approx(0.8)
    assert report.no_answer_accuracy == pytest.approx(1.0)

    by_id = {result.case_id: result for result in report.case_results}
    assert by_id["semantic-remote-work"].recall_at_5 == 0.0
    assert by_id["semantic-late-package"].recall_at_5 == 0.0
    assert by_id["no-answer-restricted-denied"].no_answer_correct is True
    assert by_id["no-answer-cross-tenant"].no_answer_correct is True
