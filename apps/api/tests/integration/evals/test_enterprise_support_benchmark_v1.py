import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tropos.capabilities.resolve.domain.knowledge_action import KnowledgeAction
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
from tropos.evals.contracts import EvalSplit
from tropos.evals.enterprise_support import (
    EnterpriseSupportBenchmark,
    load_enterprise_support_benchmark,
)
from tropos.evals.retrieval import evaluate_retrieval

DATASET = Path(__file__).parents[3] / "evals" / "resolve" / "enterprise_support_benchmark_v1.json"


def _orchestrator(store: SQLiteIngestionStore) -> IngestKnowledge:
    return IngestKnowledge(
        parser=DeterministicKnowledgeParser(),
        normalizer=DeterministicKnowledgeNormalizer(),
        chunker=DeterministicKnowledgeChunker(max_characters=2000),
        source_captures=store,
        knowledge_repository=store,
        runs=store,
    )


def _ingest_benchmark(tmp_path: Path) -> tuple[Path, EnterpriseSupportBenchmark]:
    benchmark = load_enterprise_support_benchmark(DATASET)
    database = tmp_path / "tropos.db"
    store = SQLiteIngestionStore(database)
    orchestrator = _orchestrator(store)

    for document in benchmark.knowledge_documents:
        raw = RawKnowledgeRecord(
            source_system="eval:enterprise-support-v1",
            source_record_id=f"{document.knowledge_id}.md",
            source_version=document.source_version,
            content_type="text/markdown",
            payload=document.text.encode("utf-8"),
            access_policy=document.access,
            captured_at=datetime(2026, 10, 11, tzinfo=UTC),
        )
        orchestrator.execute(
            IngestKnowledgeCommand(
                knowledge_id=document.knowledge_id,
                raw_record=raw,
            )
        )

    return database, benchmark


def test_benchmark_contains_complete_balanced_case_packs() -> None:
    benchmark = load_enterprise_support_benchmark(DATASET)

    assert benchmark.dataset_id == "tropos-enterprise-support-benchmark"
    assert benchmark.version == "1.0"
    assert len(benchmark.knowledge_documents) == 18
    assert len(benchmark.cases) == 16

    actions = Counter(case.action for case in benchmark.cases)
    assert actions == {
        KnowledgeAction.REUSE: 4,
        KnowledgeAction.IMPROVE: 4,
        KnowledgeAction.CREATE: 4,
        KnowledgeAction.NO_ACTION: 4,
    }

    for split, expected_count in (
        (EvalSplit.DEVELOPMENT, 8),
        (EvalSplit.HOLDOUT, 4),
        (EvalSplit.CHALLENGE, 4),
    ):
        cases = benchmark.cases_for_split(split)
        assert len(cases) == expected_count
        split_actions = Counter(case.action for case in cases)
        expected_per_action = 2 if split is EvalSplit.DEVELOPMENT else 1
        assert all(split_actions[action] == expected_per_action for action in KnowledgeAction)

    for case in benchmark.cases:
        record = case.case_record
        assert record["status"] == "resolved"
        assert record["short_description"]
        assert record["description"]
        assert record["environment"]
        assert record["work_notes"]
        assert record["resolution_notes"]
        assert case.research_pattern_ids


def test_benchmark_projects_balanced_retrieval_queries_without_using_holdout_by_default() -> None:
    benchmark = load_enterprise_support_benchmark(DATASET)

    development = benchmark.retrieval_cases()
    holdout = benchmark.retrieval_cases(EvalSplit.HOLDOUT)
    challenge = benchmark.retrieval_cases(EvalSplit.CHALLENGE)

    assert len(development) == 24
    assert len(holdout) == 12
    assert len(challenge) == 12

    assert sum(bool(case.relevant_knowledge_ids) for case in development) == 12
    assert sum(not case.relevant_knowledge_ids for case in development) == 12
    assert sum(bool(case.relevant_knowledge_ids) for case in holdout) == 6
    assert sum(not case.relevant_knowledge_ids for case in holdout) == 6
    assert sum(bool(case.relevant_knowledge_ids) for case in challenge) == 6
    assert sum(not case.relevant_knowledge_ids for case in challenge) == 6

    assert all(not case.case_id.startswith("ES-END-") for case in development)
    assert all(not case.case_id.startswith("ES-JSM-") for case in development)


def test_generic_retrieval_projection_binds_every_case_to_the_same_corpus() -> None:
    benchmark = load_enterprise_support_benchmark(DATASET)

    dataset = benchmark.retrieval_dataset()

    assert dataset.split is EvalSplit.DEVELOPMENT
    assert len(dataset.cases) == 24
    corpus_fingerprints = {case.inputs["corpus_fingerprint"] for case in dataset.cases}
    assert len(corpus_fingerprints) == 1


def test_benchmark_projects_resolve_decision_and_knowledge_article_datasets() -> None:
    benchmark = load_enterprise_support_benchmark(DATASET)

    decision_dev = benchmark.resolve_decision_dataset()
    article_dev = benchmark.knowledge_article_dataset()
    article_holdout = benchmark.knowledge_article_dataset(EvalSplit.HOLDOUT)
    article_challenge = benchmark.knowledge_article_dataset(EvalSplit.CHALLENGE)

    assert decision_dev.split is EvalSplit.DEVELOPMENT
    assert len(decision_dev.cases) == 8
    assert {case.expected["action"] for case in decision_dev.cases} == {
        "REUSE",
        "IMPROVE",
        "CREATE",
        "NO_ACTION",
    }

    assert len(article_dev.cases) == 4
    assert len(article_holdout.cases) == 2
    assert len(article_challenge.cases) == 2
    assert all(
        case.expected["article_type"] in {"troubleshooting", "how_to", "faq"}
        for dataset in (article_dev, article_holdout, article_challenge)
        for case in dataset.cases
    )
    assert all(
        case.inputs["reference_article"]
        for dataset in (article_dev, article_holdout, article_challenge)
        for case in dataset.cases
    )


def test_benchmark_rejects_a_create_case_that_declares_reusable_knowledge(
    tmp_path: Path,
) -> None:
    raw = json.loads(DATASET.read_text(encoding="utf-8"))
    create_case = next(case for case in raw["cases"] if case["expected"]["action"] == "CREATE")
    create_case["retrieval_queries"][0]["relevant_knowledge_ids"] = [
        "kb-entra-device-compliance-remediation"
    ]
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="CREATE case must have no reusable knowledge label"):
        load_enterprise_support_benchmark(invalid)


def test_benchmark_rejects_reference_article_with_unknown_evidence(
    tmp_path: Path,
) -> None:
    raw = json.loads(DATASET.read_text(encoding="utf-8"))
    article_case = next(case for case in raw["cases"] if case["case_id"] == "ES-ENT-002")
    reference = article_case["article_expectation"]["reference_article"]
    reference["issue_description"]["evidence_chunk_ids"] = ["missing-evidence"]
    invalid = tmp_path / "invalid-reference.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="reference article cites evidence"):
        load_enterprise_support_benchmark(invalid)


def test_bm25_can_execute_the_realistic_seed_without_crossing_restricted_boundaries(
    tmp_path: Path,
) -> None:
    database, benchmark = _ingest_benchmark(tmp_path)
    retriever = SQLiteFtsKnowledgeRetriever(database)

    for split in EvalSplit:
        cases = benchmark.retrieval_cases(split)
        report = evaluate_retrieval(retriever, cases)

        assert report.case_count == len(cases)
        assert 0.0 <= report.recall_at_1 <= 1.0
        assert 0.0 <= report.recall_at_3 <= 1.0
        assert 0.0 <= report.recall_at_5 <= 1.0
        assert 0.0 <= report.mrr <= 1.0
        assert report.no_answer_accuracy is None or 0.0 <= report.no_answer_accuracy <= 1.0

        by_id = {result.case_id: result for result in report.case_results}
        if split is EvalSplit.DEVELOPMENT:
            assert (
                "kb-security-emergency-account-rotation"
                not in by_id["NEG-DEV-006"].retrieved_knowledge_ids
            )
        if split is EvalSplit.CHALLENGE:
            assert "kb-cloud-org-policy-admin" not in by_id["NEG-CHAL-003"].retrieved_knowledge_ids
