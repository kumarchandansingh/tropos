from datetime import UTC, datetime
from hashlib import sha256

import pytest

from tropos.core.application.retrieval.models import (
    KnowledgeSearchRequest,
    RetrievalAccessContext,
    RetrievedKnowledgeChunk,
)
from tropos.core.domain.access import AccessPolicy, AccessScope
from tropos.core.domain.knowledge_chunk import KnowledgeChunk, text_fingerprint
from tropos.evals.abstention import (
    TopScoreAbstentionPolicy,
    TopScoreThresholdRetriever,
    calibrate_top_score_threshold,
    evaluate_abstention_policy,
)
from tropos.evals.contracts import (
    EvalDatasetRef,
    EvalObservation,
    EvalObservationState,
    EvalRun,
    EvalRunProvenance,
    EvalRunStatus,
    EvalScore,
    EvalScoreSource,
    EvalSubject,
)

_INVARIANTS = (
    "authorized_only",
    "current_only",
    "evidence_integrity",
    "result_contract",
)


def _score(metric: str, value: float | bool, *, passed: bool | None = None) -> EvalScore:
    return EvalScore(
        metric=metric,
        value=value,
        source=EvalScoreSource.DETERMINISTIC,
        evaluator_id="retrieval-deterministic",
        evaluator_version="v2",
        passed=passed,
    )


def _observation(
    case_id: str,
    *,
    expected: tuple[str, ...],
    top_score: float | None,
    recall_at_5: float | None,
) -> EvalObservation:
    scores = [_score(metric, True, passed=True) for metric in _INVARIANTS]
    if expected:
        assert recall_at_5 is not None
        scores.append(_score("recall_at_5", recall_at_5))
    else:
        scores.append(_score("no_answer_accuracy", 1.0 if top_score is None else 0.0))

    result_count = 0 if top_score is None else 2
    return EvalObservation(
        case_id=case_id,
        state=EvalObservationState.PASSED,
        output={
            "expected_knowledge_ids": list(expected),
            "retrieval_diagnostics": {
                "score_semantics": "strategy_native_higher_is_better",
                "result_count": result_count,
                "top_score": top_score,
                "second_score": None if top_score is None else top_score - 0.1,
                "top_score_margin": None if top_score is None else 0.1,
                "top_score_ratio": None,
            },
            "hits": [],
        },
        scores=tuple(scores),
    )


def _run(*, split: str = "development", version: str = "dense-v1") -> EvalRun:
    return EvalRun(
        run_id=f"{split}-run",
        dataset=EvalDatasetRef(
            dataset_id="enterprise-support-retrieval",
            version=f"1.0-{split}",
            fingerprint=f"{split}-fingerprint",
        ),
        subject=EvalSubject(
            subject_id="retrieval",
            version=version,
            configuration={},
        ),
        provenance=EvalRunProvenance(
            code_revision="abc",
            dependency_digest="lock",
            runtime={"dataset_split": split},
        ),
        status=EvalRunStatus.COMPLETED,
        started_at=datetime(2026, 10, 11, tzinfo=UTC),
        finished_at=datetime(2026, 10, 11, 0, 0, 1, tzinfo=UTC),
        observations=(
            _observation(
                "answerable-high",
                expected=("kb-1",),
                top_score=0.9,
                recall_at_5=1.0,
            ),
            _observation(
                "answerable-boundary",
                expected=("kb-2",),
                top_score=0.8,
                recall_at_5=1.0,
            ),
            _observation(
                "empty-near",
                expected=(),
                top_score=0.7,
                recall_at_5=None,
            ),
            _observation(
                "empty-low",
                expected=(),
                top_score=0.4,
                recall_at_5=None,
            ),
        ),
    )


def test_calibration_selects_threshold_that_preserves_required_recall() -> None:
    run = _run()

    calibration = calibrate_top_score_threshold(
        run,
        minimum_answerable_recall=1.0,
    )

    assert calibration.policy.threshold == 0.8
    assert calibration.selected.metrics.answerable_recall_at_5 == 1.0
    assert calibration.selected.metrics.unsupported_evidence_return_rate == 0.0
    assert calibration.selected.metrics.no_answer_accuracy == 1.0
    assert calibration.selected.metrics.false_abstention_rate == 0.0


def test_score_equal_to_threshold_is_returned_not_abstained() -> None:
    run = _run()
    policy = TopScoreAbstentionPolicy(
        strategy_version=run.subject.version,
        threshold=0.8,
        minimum_answerable_recall=1.0,
        calibration_dataset_id=run.dataset.dataset_id,
        calibration_dataset_version=run.dataset.version,
        calibration_dataset_fingerprint=run.dataset.fingerprint,
    )

    boundary = next(
        observation
        for observation in run.observations
        if observation.case_id == "answerable-boundary"
    )

    assert policy.abstains(boundary) is False


def test_naturally_empty_result_always_abstains() -> None:
    run = _run()
    naturally_empty = _observation(
        "naturally-empty",
        expected=(),
        top_score=None,
        recall_at_5=None,
    )
    policy = TopScoreAbstentionPolicy(
        strategy_version=run.subject.version,
        threshold=0.8,
        minimum_answerable_recall=1.0,
        calibration_dataset_id=run.dataset.dataset_id,
        calibration_dataset_version=run.dataset.version,
        calibration_dataset_fingerprint=run.dataset.fingerprint,
    )

    assert policy.abstains(naturally_empty) is True


def test_calibration_rejects_holdout_data() -> None:
    with pytest.raises(ValueError, match="development data"):
        calibrate_top_score_threshold(
            _run(split="holdout"),
            minimum_answerable_recall=0.9,
        )


def test_selected_policy_can_be_measured_on_holdout_without_recalibration() -> None:
    development = _run()
    holdout = _run(split="holdout")
    calibration = calibrate_top_score_threshold(
        development,
        minimum_answerable_recall=1.0,
    )

    metrics = evaluate_abstention_policy(holdout, calibration.policy)

    assert metrics.answerable_recall_at_5 == 1.0
    assert metrics.unsupported_evidence_return_rate == 0.0


def test_policy_is_bound_to_the_strategy_that_was_calibrated() -> None:
    development = _run()
    calibration = calibrate_top_score_threshold(
        development,
        minimum_answerable_recall=1.0,
    )

    with pytest.raises(ValueError, match="strategy"):
        evaluate_abstention_policy(
            _run(split="holdout", version="another-retriever"),
            calibration.policy,
        )


class _ResultRetriever:
    strategy_version = "dense-v1"

    def __init__(self, score: float) -> None:
        self._score = score

    def search(
        self,
        request: KnowledgeSearchRequest,
    ) -> tuple[RetrievedKnowledgeChunk, ...]:
        text = "Evidence text"
        chunk = KnowledgeChunk(
            chunk_id="chunk-1",
            knowledge_id="kb-1",
            source_system="fixture",
            source_record_id="kb-1.md",
            source_version="1",
            document_title="Evidence",
            sequence_number=0,
            text=text,
            start_offset=0,
            end_offset=len(text),
            content_fingerprint=text_fingerprint(text),
            ingestion_fingerprint=sha256(b"ingestion").hexdigest(),
            normalized_content_fingerprint=sha256(text.encode("utf-8")).hexdigest(),
            normalization_strategy_version="norm-v1",
            access_policy=AccessPolicy("tenant-a", AccessScope.TENANT),
            strategy_version="chunk-v1",
        )
        return (
            RetrievedKnowledgeChunk(
                chunk=chunk,
                rank=1,
                score=self._score,
                strategy_version=self.strategy_version,
            ),
        )


def _policy(threshold: float) -> TopScoreAbstentionPolicy:
    return TopScoreAbstentionPolicy(
        strategy_version="dense-v1",
        threshold=threshold,
        minimum_answerable_recall=0.9,
        calibration_dataset_id="dataset",
        calibration_dataset_version="v1-development",
        calibration_dataset_fingerprint="fingerprint",
    )


def test_threshold_retriever_returns_no_evidence_below_selected_score() -> None:
    retriever = TopScoreThresholdRetriever(
        retriever=_ResultRetriever(0.79),
        policy=_policy(0.8),
    )

    results = retriever.search(
        KnowledgeSearchRequest(
            query="query",
            access=RetrievalAccessContext("tenant-a"),
            limit=5,
        )
    )

    assert results == ()


def test_threshold_retriever_preserves_results_at_boundary_and_versions_output() -> None:
    retriever = TopScoreThresholdRetriever(
        retriever=_ResultRetriever(0.8),
        policy=_policy(0.8),
    )

    results = retriever.search(
        KnowledgeSearchRequest(
            query="query",
            access=RetrievalAccessContext("tenant-a"),
            limit=5,
        )
    )

    assert len(results) == 1
    assert results[0].score == 0.8
    assert results[0].strategy_version == retriever.strategy_version
