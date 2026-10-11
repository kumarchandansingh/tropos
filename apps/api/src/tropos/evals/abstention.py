"""Calibrate retrieval abstention without coupling confidence to retrieval ports."""

from __future__ import annotations

from dataclasses import dataclass
from math import inf, isfinite, nextafter

from tropos.core.application.ports.retrieval import KnowledgeChunkRetriever
from tropos.core.application.retrieval.models import (
    KnowledgeSearchRequest,
    RetrievedKnowledgeChunk,
)
from tropos.evals.contracts import EvalObservation, EvalRun, EvalRunStatus, JsonObject

_POLICY_VERSION = "top-score-threshold-v1"
_SIGNAL = "top_score"
_REQUIRED_INVARIANTS = (
    "authorized_only",
    "current_only",
    "evidence_integrity",
    "result_contract",
)


@dataclass(frozen=True, slots=True)
class AbstentionMetrics:
    """Observed selective-retrieval quality at one operating point."""

    answerable_count: int
    expected_empty_count: int
    answerable_coverage: float
    answerable_recall_at_5: float
    no_answer_accuracy: float
    false_answer_rate: float
    abstained_answerable_count: int
    abstained_expected_empty_count: int

    def as_dict(self) -> JsonObject:
        return {
            "answerable_count": self.answerable_count,
            "expected_empty_count": self.expected_empty_count,
            "answerable_coverage": self.answerable_coverage,
            "answerable_recall_at_5": self.answerable_recall_at_5,
            "no_answer_accuracy": self.no_answer_accuracy,
            "false_answer_rate": self.false_answer_rate,
            "abstained_answerable_count": self.abstained_answerable_count,
            "abstained_expected_empty_count": self.abstained_expected_empty_count,
        }


@dataclass(frozen=True, slots=True)
class TopScoreAbstentionPolicy:
    """Versioned strategy-native threshold selected from development evidence."""

    strategy_version: str
    threshold: float
    minimum_answerable_recall: float
    calibration_dataset_id: str
    calibration_dataset_version: str
    calibration_dataset_fingerprint: str
    policy_version: str = _POLICY_VERSION
    signal: str = _SIGNAL

    def __post_init__(self) -> None:
        if not self.strategy_version.strip():
            raise ValueError("strategy_version must not be blank")
        if not isfinite(self.threshold):
            raise ValueError("threshold must be finite")
        if not 0.0 <= self.minimum_answerable_recall <= 1.0:
            raise ValueError("minimum_answerable_recall must be between 0 and 1")
        for field_name, value in (
            ("calibration_dataset_id", self.calibration_dataset_id),
            ("calibration_dataset_version", self.calibration_dataset_version),
            ("calibration_dataset_fingerprint", self.calibration_dataset_fingerprint),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be blank")

    def abstains_for_score(
        self,
        *,
        result_count: int,
        top_score: float | None,
    ) -> bool:
        if type(result_count) is not int or result_count < 0:
            raise ValueError("result_count must be a non-negative integer")
        if result_count == 0:
            return True
        if isinstance(top_score, bool) or not isinstance(top_score, int | float):
            raise ValueError("non-empty retrieval results require numeric top_score")
        return float(top_score) < self.threshold

    def abstains(self, observation: EvalObservation) -> bool:
        diagnostics = _diagnostics(observation)
        result_count = diagnostics["result_count"]
        top_score = diagnostics["top_score"]
        if type(result_count) is not int:
            raise ValueError("retrieval diagnostics result_count must be an integer")
        if top_score is not None and (
            isinstance(top_score, bool) or not isinstance(top_score, int | float)
        ):
            raise ValueError("retrieval diagnostics top_score must be numeric or null")
        return self.abstains_for_score(
            result_count=result_count,
            top_score=None if top_score is None else float(top_score),
        )

    def as_dict(self) -> JsonObject:
        return {
            "policy_version": self.policy_version,
            "signal": self.signal,
            "strategy_version": self.strategy_version,
            "threshold": self.threshold,
            "comparison": "return_when_score_gte_threshold",
            "minimum_answerable_recall": self.minimum_answerable_recall,
            "calibration_dataset": {
                "dataset_id": self.calibration_dataset_id,
                "version": self.calibration_dataset_version,
                "fingerprint": self.calibration_dataset_fingerprint,
            },
        }


class TopScoreThresholdRetriever:
    """Apply a calibrated score threshold without changing the base retriever."""

    def __init__(
        self,
        *,
        retriever: KnowledgeChunkRetriever,
        policy: TopScoreAbstentionPolicy,
    ) -> None:
        if retriever.strategy_version != policy.strategy_version:
            raise ValueError("abstention policy strategy does not match base retriever")
        self._retriever = retriever
        self._policy = policy

    @property
    def strategy_version(self) -> str:
        return (
            f"{self._retriever.strategy_version}+{self._policy.policy_version}:"
            f"threshold={self._policy.threshold:.17g}"
        )

    def search(
        self,
        request: KnowledgeSearchRequest,
    ) -> tuple[RetrievedKnowledgeChunk, ...]:
        results = self._retriever.search(request)
        top_score = results[0].score if results else None
        if self._policy.abstains_for_score(
            result_count=len(results),
            top_score=top_score,
        ):
            return ()

        return tuple(
            RetrievedKnowledgeChunk(
                chunk=result.chunk,
                rank=result.rank,
                score=result.score,
                strategy_version=self.strategy_version,
            )
            for result in results
        )


@dataclass(frozen=True, slots=True)
class AbstentionOperatingPoint:
    threshold: float
    metrics: AbstentionMetrics

    def as_dict(self) -> JsonObject:
        return {
            "threshold": self.threshold,
            "metrics": self.metrics.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class AbstentionCalibration:
    policy: TopScoreAbstentionPolicy
    baseline: AbstentionOperatingPoint
    selected: AbstentionOperatingPoint
    frontier: tuple[AbstentionOperatingPoint, ...]

    def as_dict(self) -> JsonObject:
        return {
            "policy": self.policy.as_dict(),
            "baseline": self.baseline.as_dict(),
            "selected": self.selected.as_dict(),
            "frontier": [point.as_dict() for point in self.frontier],
        }


def _diagnostics(observation: EvalObservation) -> JsonObject:
    if observation.output is None:
        raise ValueError("retrieval observation requires output")
    diagnostics = observation.output.get("retrieval_diagnostics")
    if not isinstance(diagnostics, dict):
        raise ValueError("retrieval observation requires retrieval_diagnostics")
    return diagnostics


def _expected_ids(observation: EvalObservation) -> tuple[str, ...]:
    if observation.output is None:
        raise ValueError("retrieval observation requires output")
    value = observation.output.get("expected_knowledge_ids")
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("retrieval observation requires expected_knowledge_ids")
    return tuple(value)


def _score(observation: EvalObservation, metric: str) -> float:
    matches = tuple(score for score in observation.scores if score.metric == metric)
    if len(matches) != 1:
        raise ValueError(f"retrieval observation requires exactly one {metric} score")
    value = matches[0].value
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{metric} must be numeric")
    return float(value)


def _assert_valid_run(run: EvalRun) -> None:
    if run.status is not EvalRunStatus.COMPLETED:
        raise ValueError("abstention calibration/evaluation requires a completed run")
    if not run.observations:
        raise ValueError("abstention calibration/evaluation requires observations")

    for observation in run.observations:
        by_metric = {score.metric: score for score in observation.scores}
        for metric in _REQUIRED_INVARIANTS:
            score = by_metric.get(metric)
            if score is None or score.passed is not True:
                raise ValueError(
                    "abstention calibration/evaluation cannot use runs with "
                    f"hard-invariant failure: {observation.case_id}/{metric}"
                )


def evaluate_abstention_policy(
    run: EvalRun,
    policy: TopScoreAbstentionPolicy,
) -> AbstentionMetrics:
    """Measure false-answer risk and retained answerable recall after abstention."""

    _assert_valid_run(run)
    if run.subject.version != policy.strategy_version:
        raise ValueError("abstention policy strategy does not match evaluation subject")

    answerable_count = 0
    expected_empty_count = 0
    returned_answerable_count = 0
    answerable_recall_total = 0.0
    abstained_answerable_count = 0
    abstained_expected_empty_count = 0

    for observation in run.observations:
        expected = _expected_ids(observation)
        abstained = policy.abstains(observation)
        if expected:
            answerable_count += 1
            if abstained:
                abstained_answerable_count += 1
                continue
            returned_answerable_count += 1
            answerable_recall_total += _score(observation, "recall_at_5")
            continue

        expected_empty_count += 1
        if abstained:
            abstained_expected_empty_count += 1

    if answerable_count == 0 or expected_empty_count == 0:
        raise ValueError("abstention evaluation requires both answerable and expected-empty cases")

    answerable_coverage = returned_answerable_count / answerable_count
    answerable_recall_at_5 = answerable_recall_total / answerable_count
    no_answer_accuracy = abstained_expected_empty_count / expected_empty_count
    return AbstentionMetrics(
        answerable_count=answerable_count,
        expected_empty_count=expected_empty_count,
        answerable_coverage=answerable_coverage,
        answerable_recall_at_5=answerable_recall_at_5,
        no_answer_accuracy=no_answer_accuracy,
        false_answer_rate=1.0 - no_answer_accuracy,
        abstained_answerable_count=abstained_answerable_count,
        abstained_expected_empty_count=abstained_expected_empty_count,
    )


def calibrate_top_score_threshold(
    run: EvalRun,
    *,
    minimum_answerable_recall: float,
) -> AbstentionCalibration:
    """Select a top-score threshold on development data only.

    The objective is lexicographic:
    1. satisfy the caller-provided minimum answerable Recall@5;
    2. minimize false-answer rate on expected-empty cases;
    3. maximize retained answerable Recall@5;
    4. prefer the lower threshold when observed outcomes tie.
    """

    _assert_valid_run(run)
    if not 0.0 <= minimum_answerable_recall <= 1.0:
        raise ValueError("minimum_answerable_recall must be between 0 and 1")

    split = run.provenance.runtime.get("dataset_split")
    if split != "development":
        raise ValueError("abstention thresholds may only be calibrated on development data")

    top_scores: list[float] = []
    for observation in run.observations:
        diagnostics = _diagnostics(observation)
        result_count = diagnostics["result_count"]
        top_score = diagnostics["top_score"]
        if type(result_count) is not int or result_count < 0:
            raise ValueError("retrieval diagnostics result_count must be a non-negative integer")
        if result_count == 0:
            continue
        if isinstance(top_score, bool) or not isinstance(top_score, int | float):
            raise ValueError("non-empty retrieval diagnostics require numeric top_score")
        score_value = float(top_score)
        if not isfinite(score_value):
            raise ValueError("retrieval top_score must be finite")
        top_scores.append(score_value)

    if not top_scores:
        raise ValueError("calibration requires at least one non-empty retrieval result")

    minimum_score = min(top_scores)
    maximum_score = max(top_scores)
    candidate_thresholds = (
        nextafter(minimum_score, -inf),
        *sorted(set(top_scores)),
        nextafter(maximum_score, inf),
    )

    points: list[AbstentionOperatingPoint] = []
    for threshold in candidate_thresholds:
        policy = TopScoreAbstentionPolicy(
            strategy_version=run.subject.version,
            threshold=threshold,
            minimum_answerable_recall=minimum_answerable_recall,
            calibration_dataset_id=run.dataset.dataset_id,
            calibration_dataset_version=run.dataset.version,
            calibration_dataset_fingerprint=run.dataset.fingerprint,
        )
        points.append(
            AbstentionOperatingPoint(
                threshold=threshold,
                metrics=evaluate_abstention_policy(run, policy),
            )
        )

    baseline = points[0]
    feasible = tuple(
        point
        for point in points
        if point.metrics.answerable_recall_at_5 >= minimum_answerable_recall
    )
    if not feasible:
        raise ValueError(
            "no top-score threshold can satisfy the requested minimum answerable Recall@5"
        )

    selected = min(
        feasible,
        key=lambda point: (
            point.metrics.false_answer_rate,
            -point.metrics.answerable_recall_at_5,
            point.threshold,
        ),
    )
    policy = TopScoreAbstentionPolicy(
        strategy_version=run.subject.version,
        threshold=selected.threshold,
        minimum_answerable_recall=minimum_answerable_recall,
        calibration_dataset_id=run.dataset.dataset_id,
        calibration_dataset_version=run.dataset.version,
        calibration_dataset_fingerprint=run.dataset.fingerprint,
    )

    frontier = tuple(
        point
        for point in points
        if not any(
            other.metrics.answerable_recall_at_5 >= point.metrics.answerable_recall_at_5
            and other.metrics.false_answer_rate <= point.metrics.false_answer_rate
            and (
                other.metrics.answerable_recall_at_5 > point.metrics.answerable_recall_at_5
                or other.metrics.false_answer_rate < point.metrics.false_answer_rate
            )
            for other in points
        )
    )

    return AbstentionCalibration(
        policy=policy,
        baseline=baseline,
        selected=selected,
        frontier=frontier,
    )
