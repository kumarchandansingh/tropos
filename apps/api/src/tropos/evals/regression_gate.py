"""Bridge saved retrieval reports into the generic baseline/candidate gate model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from tropos.evals.catalogue import Json, array, object_value, text
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
    JsonObject,
)
from tropos.evals.experiments import (
    DecisionMetricGate,
    ExperimentComparison,
    ExperimentGatePolicy,
    HardInvariantGate,
    compare_runs,
)

_HARD_INVARIANTS = (
    "authorized_only",
    "current_only",
    "evidence_integrity",
    "result_contract",
)
_NUMERIC_DECISION_METRICS = (
    "recall_at_1",
    "recall_at_3",
    "recall_at_5",
    "precision_at_5",
    "reciprocal_rank",
)
_NO_ANSWER_METRIC = "no_answer_accuracy"


def retrieval_gate_policy() -> ExperimentGatePolicy:
    """Regression policy for the small synthetic development benchmark."""

    return ExperimentGatePolicy(
        rules=(
            *(HardInvariantGate(metric) for metric in _HARD_INVARIANTS),
            *(
                DecisionMetricGate(metric, max_mean_regression=0.0)
                for metric in (*_NUMERIC_DECISION_METRICS, _NO_ANSWER_METRIC)
            ),
        )
    )


@dataclass(frozen=True, slots=True)
class RetrievalGateDecision:
    comparison: ExperimentComparison
    baseline_revision: str
    candidate_revision: str
    case_regressions: tuple[str, ...]
    candidate_errors: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return (
            self.comparison.passed
            and not self.case_regressions
            and not self.candidate_errors
        )

    def as_dict(self) -> JsonObject:
        return {
            "schema_version": 1,
            "gate": "retrieval-regression-v1",
            "passed": self.passed,
            "baseline": {
                "run_id": self.comparison.baseline_run_id,
                "code_revision": self.baseline_revision,
            },
            "candidate": {
                "run_id": self.comparison.candidate_run_id,
                "code_revision": self.candidate_revision,
            },
            "case_regressions": list(self.case_regressions),
            "candidate_errors": list(self.candidate_errors),
            "gate_results": [
                {
                    "metric": item.metric,
                    "kind": item.kind.value,
                    "passed": item.passed,
                    "detail": item.detail,
                }
                for item in self.comparison.gate_results
            ],
            "metric_comparisons": [
                {
                    "metric": item.metric,
                    "pair_count": item.pair_count,
                    "baseline_mean": item.baseline_mean,
                    "candidate_mean": item.candidate_mean,
                    "mean_delta": item.mean_delta,
                    "confidence_low": item.confidence_low,
                    "confidence_high": item.confidence_high,
                }
                for item in self.comparison.metric_comparisons
            ],
        }

    def markdown(self) -> str:
        lines = [
            "# Retrieval regression gate",
            "",
            f"**{'PASS' if self.passed else 'FAIL'}**",
            "",
            f"- Baseline revision: `{self.baseline_revision}`",
            f"- Candidate revision: `{self.candidate_revision}`",
            f"- Case regressions: {len(self.case_regressions)}",
            f"- Candidate execution errors: {len(self.candidate_errors)}",
            "",
            "## Gate results",
            "",
            "| Dimension | Kind | Result | Detail |",
            "| --- | --- | --- | --- |",
        ]
        for result in self.comparison.gate_results:
            lines.append(
                f"| {result.metric} | {result.kind.value} | "
                f"{'pass' if result.passed else 'fail'} | {result.detail} |"
            )
        if self.case_regressions:
            lines.extend(
                [
                    "",
                    "## Regressed cases",
                    "",
                    *[f"- {case_id}" for case_id in self.case_regressions],
                ]
            )
        if self.candidate_errors:
            lines.extend(
                [
                    "",
                    "## Candidate execution errors",
                    "",
                    *[f"- {case_id}" for case_id in self.candidate_errors],
                ]
            )
        lines.extend(
            [
                "",
                "> This is a regression gate over the synthetic development set, not a "
                "release-quality accuracy claim. QE-108 supplies the larger locked benchmark.",
            ]
        )
        return "\n".join(lines) + "\n"


def compare_retrieval_reports(
    baseline_report: JsonObject,
    candidate_report: JsonObject,
) -> RetrievalGateDecision:
    """Compare two saved retrieval reports using the generic experiment layer."""

    baseline = _to_eval_run(baseline_report)
    candidate = _to_eval_run(candidate_report, baseline_run_id=baseline.run_id)
    comparison = compare_runs(
        baseline,
        candidate,
        policy=retrieval_gate_policy(),
    )
    regressions = tuple(item.case_id for item in comparison.regressions)
    errors = tuple(
        item.case_id
        for item in comparison.case_comparisons
        if item.candidate_state is EvalObservationState.ERROR
    )
    return RetrievalGateDecision(
        comparison=comparison,
        baseline_revision=baseline.provenance.code_revision,
        candidate_revision=candidate.provenance.code_revision,
        case_regressions=regressions,
        candidate_errors=errors,
    )


def _to_eval_run(report: JsonObject, *, baseline_run_id: str | None = None) -> EvalRun:
    if text(report["status"]) != EvalRunStatus.COMPLETED.value:
        raise ValueError("retrieval regression gate requires a completed saved run")

    provenance_row = object_value(report["provenance"])
    retrieval_strategy = text(provenance_row["retrieval_strategy"])
    evaluator_version = text(provenance_row["evaluator"])

    runtime: JsonObject = {}
    for key in (
        "python_version",
        "working_tree_dirty",
        "evaluator",
        "retrieval_strategy",
        "max_characters",
        "gate_policy",
        "limit",
    ):
        if key in provenance_row:
            runtime[key] = provenance_row[key]

    subject_configuration: JsonObject = {
        "retrieval_strategy": retrieval_strategy,
        "evaluator": evaluator_version,
    }
    for key in ("max_characters", "limit"):
        if key in provenance_row:
            subject_configuration[key] = provenance_row[key]

    observations = tuple(
        _to_observation(object_value(raw_case), evaluator_version)
        for raw_case in array(report["cases"])
    )

    return EvalRun(
        run_id=text(report["run_id"]),
        dataset=EvalDatasetRef(
            dataset_id=text(report["dataset_id"]),
            version=text(report["dataset_version"]),
            fingerprint=text(report["dataset_digest"]),
        ),
        subject=EvalSubject(
            subject_id="retrieval",
            version=retrieval_strategy,
            configuration=subject_configuration,
        ),
        provenance=EvalRunProvenance(
            code_revision=text(provenance_row["code_revision"]),
            dependency_digest=text(provenance_row["dependency_digest"]),
            runtime=runtime,
        ),
        status=EvalRunStatus.COMPLETED,
        started_at=datetime.fromisoformat(text(report["started"])),
        observations=observations,
        finished_at=datetime.fromisoformat(text(report["finished"])),
        baseline_run_id=baseline_run_id,
    )


def _to_observation(case: dict[str, Json], evaluator_version: str) -> EvalObservation:
    state = EvalObservationState(text(case["state"]))
    metrics_value = case.get("metrics")
    metrics = object_value(metrics_value) if metrics_value is not None else {}
    scores: list[EvalScore] = []

    for raw_assertion in array(case.get("assertions", [])):
        assertion = object_value(raw_assertion)
        passed = assertion.get("passed")
        if not isinstance(passed, bool):
            raise ValueError("saved assertion pass flag must be boolean")
        scores.append(
            EvalScore(
                metric=text(assertion["name"]),
                value=passed,
                source=EvalScoreSource.DETERMINISTIC,
                evaluator_id="saved-retrieval-assertion",
                evaluator_version=evaluator_version,
                passed=passed,
                rationale=text(assertion["detail"]),
            )
        )

    metric_version_value = metrics.get("metric_version")
    metric_version = (
        metric_version_value
        if isinstance(metric_version_value, str) and metric_version_value.strip()
        else evaluator_version
    )
    for metric in _NUMERIC_DECISION_METRICS:
        value = _numeric(metrics.get(metric))
        if value is None:
            continue
        scores.append(
            EvalScore(
                metric=metric,
                value=value,
                source=EvalScoreSource.DETERMINISTIC,
                evaluator_id="saved-retrieval-metric",
                evaluator_version=metric_version,
            )
        )

    no_answer = metrics.get("no_answer_correct")
    if isinstance(no_answer, bool):
        scores.append(
            EvalScore(
                metric=_NO_ANSWER_METRIC,
                value=1.0 if no_answer else 0.0,
                source=EvalScoreSource.DETERMINISTIC,
                evaluator_id="saved-retrieval-metric",
                evaluator_version=metric_version,
            )
        )

    duration = _numeric(case.get("duration_ms"))
    error_value = case.get("error")
    error_type = None if error_value is None else text(error_value)
    output: JsonObject = {
        "actual": case.get("actual", []),
        "definition": case.get("definition", {}),
    }

    return EvalObservation(
        case_id=text(object_value(case["definition"])["case_id"]),
        state=state,
        output=output,
        scores=tuple(scores),
        duration_ms=duration,
        error_type=error_type,
    )


def _numeric(value: Json | None) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)
