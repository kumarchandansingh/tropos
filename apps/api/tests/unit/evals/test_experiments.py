from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tropos.evals.contracts import (
    EvalApproval,
    EvalCase,
    EvalDataset,
    EvalObservation,
    EvalObservationState,
    EvalOrigin,
    EvalRunProvenance,
    EvalScope,
    EvalScore,
    EvalScoreSource,
    EvalSplit,
    EvalSubject,
)
from tropos.evals.experiment_store import SQLiteExperimentStore
from tropos.evals.experiments import (
    CaseChange,
    DecisionMetricGate,
    ExperimentGatePolicy,
    ExperimentRunner,
    GateKind,
    HardInvariantGate,
    compare_runs,
    paired_bootstrap_mean_delta,
)


def _case(case_id: str) -> EvalCase:
    return EvalCase(
        case_id=case_id,
        purpose=f"Evaluate {case_id}",
        scope=EvalScope.COMPONENT,
        approval=EvalApproval.APPROVED,
        origin=EvalOrigin.SYNTHETIC,
        inputs={"input": case_id},
        expected={"expected": True},
        tags=("fixture",),
    )


def _dataset(count: int = 2) -> EvalDataset:
    return EvalDataset(
        dataset_id="experiment-fixture",
        version="v1",
        capability="resolve",
        split=EvalSplit.DEVELOPMENT,
        cases=tuple(_case(f"case-{index:02d}") for index in range(count)),
    )


def _subject(version: str) -> EvalSubject:
    return EvalSubject(
        subject_id="knowledge-article-generator",
        version=version,
        configuration={
            "model": f"model-{version}",
            "prompt_version": f"prompt-{version}",
            "retrieval_strategy": "hybrid-rrf-v1",
        },
    )


def _provenance(revision: str) -> EvalRunProvenance:
    return EvalRunProvenance(
        code_revision=revision,
        dependency_digest="lock-digest",
        runtime={"python": "3.14"},
    )


def _score(
    metric: str,
    value: float | bool,
    *,
    passed: bool | None = None,
) -> EvalScore:
    return EvalScore(
        metric=metric,
        value=value,
        source=EvalScoreSource.DETERMINISTIC,
        evaluator_id="fixture-evaluator",
        evaluator_version="v1",
        passed=passed,
    )


class _Executor:
    def __init__(
        self,
        *,
        quality: float,
        invariant_passed: bool = True,
        fail_case: str | None = None,
    ) -> None:
        self.quality = quality
        self.invariant_passed = invariant_passed
        self.fail_case = fail_case

    def execute(self, case: EvalCase) -> EvalObservation:
        failed = case.case_id == self.fail_case
        return EvalObservation(
            case_id=case.case_id,
            state=EvalObservationState.FAILED if failed else EvalObservationState.PASSED,
            output={"subject_output": case.case_id},
            scores=(
                _score("quality", self.quality, passed=not failed),
                _score(
                    "evidence_integrity",
                    self.invariant_passed,
                    passed=self.invariant_passed,
                ),
            ),
            duration_ms=12.5,
        )


def _clock() -> Callable[[], datetime]:
    moments = iter(
        (
            datetime(2026, 10, 10, 12, 0, tzinfo=UTC),
            datetime(2026, 10, 10, 12, 0, tzinfo=UTC) + timedelta(seconds=1),
        )
    )
    return lambda: next(moments)


def test_runner_records_subject_provenance_and_observations() -> None:
    dataset = _dataset()
    runner = ExperimentRunner(
        clock=_clock(),
        run_id_factory=lambda: "run-baseline",
    )

    run = runner.run(
        dataset=dataset,
        subject=_subject("v1"),
        provenance=_provenance("abc123"),
        executor=_Executor(quality=0.8),
    )

    assert run.run_id == "run-baseline"
    assert run.dataset.fingerprint == dataset.fingerprint
    assert run.subject.configuration["prompt_version"] == "prompt-v1"
    assert run.provenance.code_revision == "abc123"
    assert [item.state for item in run.observations] == [
        EvalObservationState.PASSED,
        EvalObservationState.PASSED,
    ]


def test_compare_runs_detects_case_regression_and_improvement() -> None:
    dataset = _dataset(2)
    baseline = ExperimentRunner(
        clock=_clock(),
        run_id_factory=lambda: "baseline",
    ).run(
        dataset=dataset,
        subject=_subject("v1"),
        provenance=_provenance("baseline-rev"),
        executor=_Executor(quality=0.8, fail_case="case-01"),
    )
    candidate = ExperimentRunner(
        clock=_clock(),
        run_id_factory=lambda: "candidate",
    ).run(
        dataset=dataset,
        subject=_subject("v2"),
        provenance=_provenance("candidate-rev"),
        executor=_Executor(quality=0.9, fail_case="case-00"),
        baseline_run_id=baseline.run_id,
    )

    comparison = compare_runs(baseline, candidate)

    changes = {item.case_id: item.change for item in comparison.case_comparisons}
    assert changes == {
        "case-00": CaseChange.REGRESSION,
        "case-01": CaseChange.IMPROVEMENT,
    }
    quality = next(item for item in comparison.metric_comparisons if item.metric == "quality")
    assert quality.pair_count == 2
    assert quality.baseline_mean == 0.8
    assert quality.candidate_mean == 0.9
    assert quality.mean_delta == pytest.approx(0.1)
    assert quality.confidence_low is None
    assert quality.confidence_high is None


def test_paired_bootstrap_reports_deterministic_interval_for_paired_delta() -> None:
    baseline = tuple(0.8 for _ in range(20))
    candidate = tuple(0.85 for _ in range(20))

    interval = paired_bootstrap_mean_delta(
        baseline,
        candidate,
        samples=500,
        seed=7,
    )

    assert interval[0] == interval[1]
    assert round(interval[0], 6) == 0.05


def test_gate_policy_separates_hard_invariant_and_decision_metric() -> None:
    dataset = _dataset(20)
    baseline = ExperimentRunner(
        clock=_clock(),
        run_id_factory=lambda: "baseline",
    ).run(
        dataset=dataset,
        subject=_subject("v1"),
        provenance=_provenance("baseline-rev"),
        executor=_Executor(quality=0.8),
    )
    candidate = ExperimentRunner(
        clock=_clock(),
        run_id_factory=lambda: "candidate",
    ).run(
        dataset=dataset,
        subject=_subject("v2"),
        provenance=_provenance("candidate-rev"),
        executor=_Executor(quality=0.7, invariant_passed=False),
        baseline_run_id=baseline.run_id,
    )

    comparison = compare_runs(
        baseline,
        candidate,
        policy=ExperimentGatePolicy(
            rules=(
                HardInvariantGate("evidence_integrity"),
                DecisionMetricGate("quality", max_mean_regression=0.02),
            )
        ),
        bootstrap_samples=500,
    )

    by_kind = {result.kind: result for result in comparison.gate_results}
    assert by_kind[GateKind.HARD_INVARIANT].passed is False
    assert by_kind[GateKind.DECISION_METRIC].passed is False
    quality = next(item for item in comparison.metric_comparisons if item.metric == "quality")
    assert quality.confidence_low is not None
    assert quality.confidence_high is not None
    assert comparison.passed is False


def test_sqlite_experiment_store_round_trips_per_case_observations(tmp_path: Path) -> None:
    store = SQLiteExperimentStore(tmp_path / "experiments.sqlite")
    dataset = _dataset()
    run = ExperimentRunner(
        sink=store,
        clock=_clock(),
        run_id_factory=lambda: "persisted-run",
    ).run(
        dataset=dataset,
        subject=_subject("v1"),
        provenance=_provenance("abc123"),
        executor=_Executor(quality=0.8),
        baseline_run_id="prior-run",
    )

    restored = store.load(run.run_id)

    assert restored == run
    assert restored.baseline_run_id == "prior-run"
    assert restored.observations[0].scores[0].metric == "quality"


def test_compare_runs_distinguishes_unchanged_from_incomparable() -> None:
    dataset = _dataset(1)
    baseline = ExperimentRunner(
        clock=_clock(),
        run_id_factory=lambda: "baseline",
    ).run(
        dataset=dataset,
        subject=_subject("v1"),
        provenance=_provenance("baseline-rev"),
        executor=_Executor(quality=0.8),
    )
    unchanged_candidate = ExperimentRunner(
        clock=_clock(),
        run_id_factory=lambda: "candidate-unchanged",
    ).run(
        dataset=dataset,
        subject=_subject("v2"),
        provenance=_provenance("candidate-rev"),
        executor=_Executor(quality=0.8),
        baseline_run_id=baseline.run_id,
    )

    unchanged = compare_runs(baseline, unchanged_candidate)
    assert unchanged.case_comparisons[0].change is CaseChange.UNCHANGED

    not_run_observation = replace(
        unchanged_candidate.observations[0],
        state=EvalObservationState.NOT_RUN,
        scores=(),
    )
    incomparable_candidate = replace(
        unchanged_candidate,
        run_id="candidate-incomparable",
        observations=(not_run_observation,),
    )

    incomparable = compare_runs(baseline, incomparable_candidate)
    assert incomparable.case_comparisons[0].change is CaseChange.INCOMPARABLE


def test_decision_metric_allows_regression_exactly_at_budget_boundary() -> None:
    dataset = _dataset(2)
    baseline = ExperimentRunner(
        clock=_clock(),
        run_id_factory=lambda: "baseline",
    ).run(
        dataset=dataset,
        subject=_subject("v1"),
        provenance=_provenance("baseline-rev"),
        executor=_Executor(quality=0.8),
    )
    candidate = ExperimentRunner(
        clock=_clock(),
        run_id_factory=lambda: "candidate",
    ).run(
        dataset=dataset,
        subject=_subject("v2"),
        provenance=_provenance("candidate-rev"),
        executor=_Executor(quality=0.78),
        baseline_run_id=baseline.run_id,
    )

    comparison = compare_runs(
        baseline,
        candidate,
        policy=ExperimentGatePolicy(
            rules=(DecisionMetricGate("quality", max_mean_regression=0.02),)
        ),
    )

    assert comparison.gate_results[0].passed is True
    assert comparison.metric_comparisons[0].mean_delta == pytest.approx(-0.02)


def test_paired_bootstrap_pins_both_interval_endpoints() -> None:
    baseline = tuple(0.0 for _ in range(20))
    candidate = tuple([0.0] * 10 + [1.0] * 10)

    interval = paired_bootstrap_mean_delta(
        baseline,
        candidate,
        samples=500,
        seed=7,
    )

    assert interval == pytest.approx((0.3, 0.7))
