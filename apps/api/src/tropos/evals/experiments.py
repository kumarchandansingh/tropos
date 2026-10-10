"""Generic baseline-versus-candidate evaluation experiments."""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from statistics import fmean
from typing import Protocol
from uuid import uuid4

from tropos.evals.contracts import (
    EvalCase,
    EvalDataset,
    EvalDatasetRef,
    EvalObservation,
    EvalObservationState,
    EvalRun,
    EvalRunProvenance,
    EvalRunStatus,
    EvalScore,
    EvalSubject,
)


class EvalCaseExecutor(Protocol):
    """Execute one evaluation case and return a terminal observation."""

    def execute(self, case: EvalCase) -> EvalObservation: ...


class EvalRunSink(Protocol):
    """Persist one completed or interrupted evaluation run."""

    def save(self, run: EvalRun) -> None: ...


class CaseChange(StrEnum):
    REGRESSION = "regression"
    IMPROVEMENT = "improvement"
    UNCHANGED = "unchanged"
    INCOMPARABLE = "incomparable"


class GateKind(StrEnum):
    HARD_INVARIANT = "hard_invariant"
    DECISION_METRIC = "decision_metric"


@dataclass(frozen=True, slots=True)
class HardInvariantGate:
    metric: str

    def __post_init__(self) -> None:
        if not self.metric.strip():
            raise ValueError("metric must not be blank")


@dataclass(frozen=True, slots=True)
class DecisionMetricGate:
    metric: str
    max_mean_regression: float = 0.0

    def __post_init__(self) -> None:
        if not self.metric.strip():
            raise ValueError("metric must not be blank")
        if self.max_mean_regression < 0:
            raise ValueError("max_mean_regression must not be negative")


type GateRule = HardInvariantGate | DecisionMetricGate


@dataclass(frozen=True, slots=True)
class ExperimentGatePolicy:
    rules: tuple[GateRule, ...] = ()


@dataclass(frozen=True, slots=True)
class CaseComparison:
    case_id: str
    baseline_state: EvalObservationState
    candidate_state: EvalObservationState
    change: CaseChange


@dataclass(frozen=True, slots=True)
class MetricComparison:
    metric: str
    pair_count: int
    baseline_mean: float
    candidate_mean: float
    mean_delta: float
    confidence_low: float | None
    confidence_high: float | None


@dataclass(frozen=True, slots=True)
class GateResult:
    metric: str
    kind: GateKind
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class ExperimentComparison:
    baseline_run_id: str
    candidate_run_id: str
    case_comparisons: tuple[CaseComparison, ...]
    metric_comparisons: tuple[MetricComparison, ...]
    gate_results: tuple[GateResult, ...]

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.gate_results)

    @property
    def regressions(self) -> tuple[CaseComparison, ...]:
        return tuple(item for item in self.case_comparisons if item.change is CaseChange.REGRESSION)

    @property
    def improvements(self) -> tuple[CaseComparison, ...]:
        return tuple(
            item for item in self.case_comparisons if item.change is CaseChange.IMPROVEMENT
        )


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _new_run_id() -> str:
    return uuid4().hex


class ExperimentRunner:
    """Run one subject over one immutable dataset snapshot."""

    def __init__(
        self,
        *,
        sink: EvalRunSink | None = None,
        clock: Callable[[], datetime] = _utc_now,
        run_id_factory: Callable[[], str] = _new_run_id,
    ) -> None:
        self._sink = sink
        self._clock = clock
        self._run_id_factory = run_id_factory

    def run(
        self,
        *,
        dataset: EvalDataset,
        subject: EvalSubject,
        provenance: EvalRunProvenance,
        executor: EvalCaseExecutor,
        baseline_run_id: str | None = None,
    ) -> EvalRun:
        started_at = self._clock()
        observations: list[EvalObservation] = []

        for case in dataset.cases:
            try:
                observation = executor.execute(case)
            except Exception as exc:
                observation = EvalObservation(
                    case_id=case.case_id,
                    state=EvalObservationState.ERROR,
                    error_type=type(exc).__name__,
                )

            if observation.case_id != case.case_id:
                raise ValueError("executor returned an observation for the wrong case")
            if observation.state not in {
                EvalObservationState.PASSED,
                EvalObservationState.FAILED,
                EvalObservationState.ERROR,
            }:
                raise ValueError("executor must return a terminal observation")
            observations.append(observation)

        run = EvalRun(
            run_id=self._run_id_factory(),
            dataset=EvalDatasetRef.from_dataset(dataset),
            subject=subject,
            provenance=provenance,
            status=EvalRunStatus.COMPLETED,
            started_at=started_at,
            observations=tuple(observations),
            finished_at=self._clock(),
            baseline_run_id=baseline_run_id,
        )
        if self._sink is not None:
            self._sink.save(run)
        return run


def compare_runs(
    baseline: EvalRun,
    candidate: EvalRun,
    *,
    policy: ExperimentGatePolicy | None = None,
    bootstrap_samples: int = 2000,
    bootstrap_confidence: float = 0.95,
    minimum_bootstrap_pairs: int = 20,
    bootstrap_seed: int = 0,
) -> ExperimentComparison:
    """Compare two runs over the same dataset and evaluate optional gate rules."""

    _validate_comparable_runs(baseline, candidate)

    baseline_by_case = {item.case_id: item for item in baseline.observations}
    candidate_by_case = {item.case_id: item for item in candidate.observations}
    case_ids = sorted(set(baseline_by_case) | set(candidate_by_case))

    cases = tuple(
        CaseComparison(
            case_id=case_id,
            baseline_state=baseline_by_case[case_id].state,
            candidate_state=candidate_by_case[case_id].state,
            change=_case_change(
                baseline_by_case[case_id].state,
                candidate_by_case[case_id].state,
            ),
        )
        for case_id in case_ids
    )

    metric_pairs = _metric_pairs(baseline_by_case, candidate_by_case)
    metrics: list[MetricComparison] = []
    for metric in sorted(metric_pairs):
        pairs = metric_pairs[metric]
        baseline_values = tuple(pair[0] for pair in pairs)
        candidate_values = tuple(pair[1] for pair in pairs)
        interval = (
            paired_bootstrap_mean_delta(
                baseline_values,
                candidate_values,
                samples=bootstrap_samples,
                confidence=bootstrap_confidence,
                seed=_metric_seed(bootstrap_seed, metric),
            )
            if len(pairs) >= minimum_bootstrap_pairs
            else None
        )
        baseline_mean = fmean(baseline_values)
        candidate_mean = fmean(candidate_values)
        metrics.append(
            MetricComparison(
                metric=metric,
                pair_count=len(pairs),
                baseline_mean=baseline_mean,
                candidate_mean=candidate_mean,
                mean_delta=candidate_mean - baseline_mean,
                confidence_low=None if interval is None else interval[0],
                confidence_high=None if interval is None else interval[1],
            )
        )

    metric_by_name = {item.metric: item for item in metrics}
    resolved_policy = policy if policy is not None else ExperimentGatePolicy()
    gate_results = tuple(
        _evaluate_gate(rule, candidate, metric_by_name) for rule in resolved_policy.rules
    )

    return ExperimentComparison(
        baseline_run_id=baseline.run_id,
        candidate_run_id=candidate.run_id,
        case_comparisons=cases,
        metric_comparisons=tuple(metrics),
        gate_results=gate_results,
    )


def paired_bootstrap_mean_delta(
    baseline: tuple[float, ...],
    candidate: tuple[float, ...],
    *,
    samples: int = 2000,
    confidence: float = 0.95,
    seed: int = 0,
) -> tuple[float, float]:
    """Deterministic paired bootstrap interval for candidate minus baseline mean."""

    if not baseline or len(baseline) != len(candidate):
        raise ValueError("paired bootstrap requires equally sized non-empty samples")
    if samples < 100:
        raise ValueError("bootstrap samples must be at least 100")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between zero and one")

    deltas = tuple(after - before for before, after in zip(baseline, candidate, strict=True))
    rng = random.Random(seed)
    estimates = sorted(fmean(rng.choice(deltas) for _ in deltas) for _ in range(samples))

    tail = (1.0 - confidence) / 2.0
    lower_index = min(samples - 1, max(0, int(tail * samples)))
    upper_index = min(samples - 1, max(0, int((1.0 - tail) * samples) - 1))
    return estimates[lower_index], estimates[upper_index]


def _validate_comparable_runs(baseline: EvalRun, candidate: EvalRun) -> None:
    if baseline.status is not EvalRunStatus.COMPLETED:
        raise ValueError("baseline run must be completed")
    if candidate.status is not EvalRunStatus.COMPLETED:
        raise ValueError("candidate run must be completed")
    if baseline.dataset != candidate.dataset:
        raise ValueError("baseline and candidate must use the same dataset snapshot")
    baseline_cases = {item.case_id for item in baseline.observations}
    candidate_cases = {item.case_id for item in candidate.observations}
    if baseline_cases != candidate_cases:
        raise ValueError("baseline and candidate must contain the same case IDs")
    if candidate.baseline_run_id not in {None, baseline.run_id}:
        raise ValueError("candidate baseline_run_id does not match the baseline run")


def _case_change(
    baseline: EvalObservationState,
    candidate: EvalObservationState,
) -> CaseChange:
    if candidate is EvalObservationState.ERROR and baseline is not EvalObservationState.ERROR:
        return CaseChange.REGRESSION
    if baseline is EvalObservationState.ERROR and candidate is not EvalObservationState.ERROR:
        return CaseChange.IMPROVEMENT
    if baseline is EvalObservationState.PASSED and candidate is EvalObservationState.FAILED:
        return CaseChange.REGRESSION
    if baseline is EvalObservationState.FAILED and candidate is EvalObservationState.PASSED:
        return CaseChange.IMPROVEMENT
    if baseline is candidate:
        return CaseChange.UNCHANGED
    return CaseChange.INCOMPARABLE


def _numeric_scores(observation: EvalObservation) -> dict[str, float]:
    scores: dict[str, float] = {}
    for score in observation.scores:
        if isinstance(score.value, bool):
            continue
        if score.metric in scores:
            raise ValueError(f"duplicate numeric score metric: {score.metric}")
        scores[score.metric] = float(score.value)
    return scores


def _metric_pairs(
    baseline_by_case: dict[str, EvalObservation],
    candidate_by_case: dict[str, EvalObservation],
) -> dict[str, list[tuple[float, float]]]:
    pairs: dict[str, list[tuple[float, float]]] = {}
    for case_id in sorted(baseline_by_case):
        baseline_scores = _numeric_scores(baseline_by_case[case_id])
        candidate_scores = _numeric_scores(candidate_by_case[case_id])
        for metric in sorted(set(baseline_scores) & set(candidate_scores)):
            pairs.setdefault(metric, []).append((baseline_scores[metric], candidate_scores[metric]))
    return pairs


def _candidate_scores(run: EvalRun, metric: str) -> tuple[EvalScore, ...]:
    return tuple(
        score
        for observation in run.observations
        for score in observation.scores
        if score.metric == metric
    )


def _evaluate_gate(
    rule: GateRule,
    candidate: EvalRun,
    metric_by_name: dict[str, MetricComparison],
) -> GateResult:
    if isinstance(rule, HardInvariantGate):
        scores = _candidate_scores(candidate, rule.metric)
        passed = bool(scores) and all(score.passed is True for score in scores)
        detail = (
            f"{len(scores)} candidate score(s); every score must explicitly pass"
            if scores
            else "candidate produced no score for this invariant"
        )
        return GateResult(rule.metric, GateKind.HARD_INVARIANT, passed, detail)

    comparison = metric_by_name.get(rule.metric)
    if comparison is None:
        return GateResult(
            rule.metric,
            GateKind.DECISION_METRIC,
            False,
            "no paired numeric observations for this metric",
        )
    passed = comparison.mean_delta >= -rule.max_mean_regression
    detail = (
        f"mean delta={comparison.mean_delta:.6f}; "
        f"allowed regression={rule.max_mean_regression:.6f}; "
        f"pairs={comparison.pair_count}"
    )
    return GateResult(rule.metric, GateKind.DECISION_METRIC, passed, detail)


def _metric_seed(base_seed: int, metric: str) -> int:
    digest = sha256(f"{base_seed}:{metric}".encode()).digest()
    return int.from_bytes(digest[:8], "big")
