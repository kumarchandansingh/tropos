"""JSON serialization for generic evaluation runs."""

from __future__ import annotations

from datetime import datetime

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
    JsonValue,
)


def eval_run_to_dict(run: EvalRun) -> JsonObject:
    return {
        "schema_version": 1,
        "run_id": run.run_id,
        "dataset": {
            "dataset_id": run.dataset.dataset_id,
            "version": run.dataset.version,
            "fingerprint": run.dataset.fingerprint,
        },
        "subject": {
            "subject_id": run.subject.subject_id,
            "version": run.subject.version,
            "configuration": run.subject.configuration,
        },
        "provenance": {
            "code_revision": run.provenance.code_revision,
            "dependency_digest": run.provenance.dependency_digest,
            "runtime": run.provenance.runtime,
        },
        "status": run.status.value,
        "started_at": run.started_at.isoformat(),
        "finished_at": None if run.finished_at is None else run.finished_at.isoformat(),
        "baseline_run_id": run.baseline_run_id,
        "observations": [
            {
                "case_id": observation.case_id,
                "state": observation.state.value,
                "output": observation.output,
                "scores": [
                    {
                        "metric": score.metric,
                        "value": score.value,
                        "source": score.source.value,
                        "evaluator_id": score.evaluator_id,
                        "evaluator_version": score.evaluator_version,
                        "passed": score.passed,
                        "rationale": score.rationale,
                    }
                    for score in observation.scores
                ],
                "duration_ms": observation.duration_ms,
                "error_type": observation.error_type,
            }
            for observation in run.observations
        ],
    }


def _object(value: JsonValue) -> JsonObject:
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    return value


def _array(value: JsonValue) -> list[JsonValue]:
    if not isinstance(value, list):
        raise ValueError("expected JSON array")
    return value


def _text(value: JsonValue) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("expected non-empty text")
    return value


def _optional_text(value: JsonValue) -> str | None:
    if value is None:
        return None
    return _text(value)


def _number(value: JsonValue) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("expected numeric value")
    return float(value)


def _score_value(value: JsonValue) -> float | bool:
    if isinstance(value, bool):
        return value
    return _number(value)


def eval_run_from_dict(value: JsonObject) -> EvalRun:
    if value.get("schema_version") != 1:
        raise ValueError("generic evaluation run requires schema_version 1")

    dataset = _object(value["dataset"])
    subject = _object(value["subject"])
    provenance = _object(value["provenance"])

    observations: list[EvalObservation] = []
    for raw_observation in _array(value["observations"]):
        observation = _object(raw_observation)
        scores: list[EvalScore] = []
        for raw_score in _array(observation["scores"]):
            score = _object(raw_score)
            passed = score["passed"]
            if passed is not None and not isinstance(passed, bool):
                raise ValueError("score passed must be boolean or null")
            rationale = score["rationale"]
            scores.append(
                EvalScore(
                    metric=_text(score["metric"]),
                    value=_score_value(score["value"]),
                    source=EvalScoreSource(_text(score["source"])),
                    evaluator_id=_text(score["evaluator_id"]),
                    evaluator_version=_text(score["evaluator_version"]),
                    passed=passed,
                    rationale=_optional_text(rationale),
                )
            )

        output_raw = observation["output"]
        observations.append(
            EvalObservation(
                case_id=_text(observation["case_id"]),
                state=EvalObservationState(_text(observation["state"])),
                output=None if output_raw is None else _object(output_raw),
                scores=tuple(scores),
                duration_ms=(
                    None
                    if observation["duration_ms"] is None
                    else _number(observation["duration_ms"])
                ),
                error_type=_optional_text(observation["error_type"]),
            )
        )

    finished_raw = value["finished_at"]
    return EvalRun(
        run_id=_text(value["run_id"]),
        dataset=EvalDatasetRef(
            dataset_id=_text(dataset["dataset_id"]),
            version=_text(dataset["version"]),
            fingerprint=_text(dataset["fingerprint"]),
        ),
        subject=EvalSubject(
            subject_id=_text(subject["subject_id"]),
            version=_text(subject["version"]),
            configuration=_object(subject["configuration"]),
        ),
        provenance=EvalRunProvenance(
            code_revision=_text(provenance["code_revision"]),
            dependency_digest=_text(provenance["dependency_digest"]),
            runtime=_object(provenance["runtime"]),
        ),
        status=EvalRunStatus(_text(value["status"])),
        started_at=datetime.fromisoformat(_text(value["started_at"])),
        observations=tuple(observations),
        finished_at=(
            None
            if finished_raw is None
            else datetime.fromisoformat(_text(finished_raw))
        ),
        baseline_run_id=_optional_text(value["baseline_run_id"]),
    )
