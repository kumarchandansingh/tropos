from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from tropos.evals.contracts import (
    EvalApproval,
    EvalCase,
    EvalDataset,
    EvalDatasetRef,
    EvalObservation,
    EvalObservationState,
    EvalOrigin,
    EvalRun,
    EvalRunProvenance,
    EvalRunStatus,
    EvalScope,
    EvalScore,
    EvalScoreSource,
    EvalSplit,
    EvalSubject,
    validate_run_transition,
)


def _case(
    *,
    approval: EvalApproval = EvalApproval.APPROVED,
    expected_action: str = "check_status",
) -> EvalCase:
    return EvalCase(
        case_id="case-1",
        purpose="Validate payment-resolution workflow",
        scope=EvalScope.COMPONENT,
        approval=approval,
        origin=EvalOrigin.SYNTHETIC,
        inputs={"case_text": "Payment debited but merchant not credited"},
        expected={"action": expected_action},
        tags=("payments", "critical"),
    )


def _dataset(case: EvalCase | None = None) -> EvalDataset:
    return EvalDataset(
        dataset_id="resolve-nba",
        version="v1",
        capability="resolve",
        split=EvalSplit.DEVELOPMENT,
        cases=(case or _case(),),
    )


def _subject() -> EvalSubject:
    return EvalSubject(
        subject_id="resolve-nba",
        version="v3",
        configuration={
            "prompt_version": "p2",
            "model": "test-model",
            "retrieval_strategy": "hybrid-v1",
        },
    )


def _provenance() -> EvalRunProvenance:
    return EvalRunProvenance(
        code_revision="abc123",
        dependency_digest="lock-456",
        runtime={"python": "3.14", "environment": "ci"},
    )


def test_case_fingerprint_is_stable_for_equivalent_json_key_order() -> None:
    first = EvalCase(
        case_id="case-1",
        purpose="Stable fingerprint",
        scope=EvalScope.COMPONENT,
        approval=EvalApproval.APPROVED,
        origin=EvalOrigin.HUMAN_AUTHORED,
        inputs={"b": 2, "a": 1},
        expected={"y": True, "x": "value"},
    )
    second = EvalCase(
        case_id="case-1",
        purpose="Stable fingerprint",
        scope=EvalScope.COMPONENT,
        approval=EvalApproval.APPROVED,
        origin=EvalOrigin.HUMAN_AUTHORED,
        inputs={"a": 1, "b": 2},
        expected={"x": "value", "y": True},
    )

    assert first.fingerprint == second.fingerprint


def test_candidate_and_approved_case_are_distinct_dataset_content() -> None:
    candidate = _dataset(_case(approval=EvalApproval.CANDIDATE))
    approved = _dataset(_case(approval=EvalApproval.APPROVED))

    assert candidate.fingerprint != approved.fingerprint
    assert candidate.cases[0].approval is EvalApproval.CANDIDATE
    assert approved.cases[0].approval is EvalApproval.APPROVED


def test_dataset_fingerprint_changes_when_expected_behavior_changes() -> None:
    baseline = _dataset(_case(expected_action="check_status"))
    changed = _dataset(_case(expected_action="refund"))

    assert baseline.fingerprint != changed.fingerprint


def test_dataset_requires_unique_case_ids() -> None:
    duplicate = _case()

    with pytest.raises(ValueError, match="unique"):
        EvalDataset(
            dataset_id="resolve-nba",
            version="v1",
            capability="resolve",
            split=EvalSplit.DEVELOPMENT,
            cases=(duplicate, duplicate),
        )


@pytest.mark.parametrize(
    "source",
    [
        EvalScoreSource.DETERMINISTIC,
        EvalScoreSource.MODEL_JUDGE,
        EvalScoreSource.HUMAN,
    ],
)
def test_score_records_source_and_evaluator_version(source: EvalScoreSource) -> None:
    score = EvalScore(
        metric="groundedness",
        value=0.9,
        source=source,
        evaluator_id="grounding-evaluator",
        evaluator_version="v2",
        passed=True,
    )

    assert score.source is source
    assert score.evaluator_version == "v2"


def test_score_contract_is_immutable() -> None:
    score = EvalScore(
        metric="workflow_accuracy",
        value=True,
        source=EvalScoreSource.DETERMINISTIC,
        evaluator_id="workflow-exact-match",
        evaluator_version="v1",
    )

    with pytest.raises(FrozenInstanceError):
        score.metric = "changed"  # type: ignore[misc]


def test_error_observation_requires_safe_error_type() -> None:
    with pytest.raises(ValueError, match="error_type"):
        EvalObservation(
            case_id="case-1",
            state=EvalObservationState.ERROR,
        )

    observation = EvalObservation(
        case_id="case-1",
        state=EvalObservationState.ERROR,
        error_type="TimeoutError",
        duration_ms=120.0,
    )

    assert observation.error_type == "TimeoutError"


def test_non_terminal_observation_cannot_record_scores() -> None:
    score = EvalScore(
        metric="workflow_accuracy",
        value=True,
        source=EvalScoreSource.DETERMINISTIC,
        evaluator_id="workflow-exact-match",
        evaluator_version="v1",
    )

    with pytest.raises(ValueError, match="non-terminal"):
        EvalObservation(
            case_id="case-1",
            state=EvalObservationState.RUNNING,
            scores=(score,),
        )


def test_run_keeps_provenance_separate_from_observed_output() -> None:
    started = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)
    finished = started + timedelta(seconds=3)
    observation = EvalObservation(
        case_id="case-1",
        state=EvalObservationState.PASSED,
        output={"recommended_action": "check_status"},
        scores=(
            EvalScore(
                metric="action_correct",
                value=True,
                source=EvalScoreSource.DETERMINISTIC,
                evaluator_id="action-match",
                evaluator_version="v1",
                passed=True,
            ),
        ),
    )
    run = EvalRun(
        run_id="run-1",
        dataset=EvalDatasetRef.from_dataset(_dataset()),
        subject=_subject(),
        provenance=_provenance(),
        status=EvalRunStatus.COMPLETED,
        started_at=started,
        finished_at=finished,
        observations=(observation,),
    )

    assert run.provenance.code_revision == "abc123"
    assert run.observations[0].output == {"recommended_action": "check_status"}
    assert "recommended_action" not in run.provenance.runtime


def test_run_state_contract_rejects_invalid_terminal_timestamps() -> None:
    started = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)

    with pytest.raises(ValueError, match="finished_at"):
        EvalRun(
            run_id="run-1",
            dataset=EvalDatasetRef.from_dataset(_dataset()),
            subject=_subject(),
            provenance=_provenance(),
            status=EvalRunStatus.COMPLETED,
            started_at=started,
        )

    with pytest.raises(ValueError, match="cannot have finished_at"):
        EvalRun(
            run_id="run-2",
            dataset=EvalDatasetRef.from_dataset(_dataset()),
            subject=_subject(),
            provenance=_provenance(),
            status=EvalRunStatus.RUNNING,
            started_at=started,
            finished_at=started,
        )


def test_run_transition_only_allows_running_to_terminal() -> None:
    validate_run_transition(EvalRunStatus.RUNNING, EvalRunStatus.COMPLETED)
    validate_run_transition(EvalRunStatus.RUNNING, EvalRunStatus.INTERRUPTED)

    with pytest.raises(ValueError, match="invalid evaluation run transition"):
        validate_run_transition(EvalRunStatus.COMPLETED, EvalRunStatus.RUNNING)
