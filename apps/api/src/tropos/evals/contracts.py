"""Vendor-neutral evaluation contracts shared across Tropos capabilities."""

import json
import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import Protocol

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]


def canonical_json(value: JsonValue) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("evaluation payload must be canonical JSON data") from exc


def fingerprint(value: JsonValue) -> str:
    return sha256(canonical_json(value).encode()).hexdigest()


def _non_blank(field_name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")


def _aware(field_name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include timezone information")


class EvalSplit(StrEnum):
    DEVELOPMENT = "development"
    HOLDOUT = "holdout"
    CHALLENGE = "challenge"


class EvalApproval(StrEnum):
    CANDIDATE = "candidate"
    APPROVED = "approved"


class EvalOrigin(StrEnum):
    SYNTHETIC = "synthetic"
    HUMAN_AUTHORED = "human_authored"
    PRODUCTION_DERIVED = "production_derived"


class EvalScope(StrEnum):
    COMPONENT = "component"
    END_TO_END = "end_to_end"


class EvalScoreSource(StrEnum):
    DETERMINISTIC = "deterministic"
    MODEL_JUDGE = "model_judge"
    HUMAN = "human"


class EvalRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"


class EvalObservationState(StrEnum):
    NOT_RUN = "not_run"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class EvalCase:
    case_id: str
    purpose: str
    scope: EvalScope
    approval: EvalApproval
    origin: EvalOrigin
    inputs: JsonObject
    expected: JsonObject
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _non_blank("case_id", self.case_id)
        _non_blank("purpose", self.purpose)
        if any(not tag.strip() for tag in self.tags):
            raise ValueError("tags must not contain blank values")
        if len(set(self.tags)) != len(self.tags):
            raise ValueError("tags must not contain duplicates")
        canonical_json(self.inputs)
        canonical_json(self.expected)

    def snapshot(self) -> JsonObject:
        return {
            "case_id": self.case_id,
            "purpose": self.purpose,
            "scope": self.scope.value,
            "approval": self.approval.value,
            "origin": self.origin.value,
            "inputs": self.inputs,
            "expected": self.expected,
            "tags": list(self.tags),
        }

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.snapshot())


@dataclass(frozen=True, slots=True)
class EvalDataset:
    dataset_id: str
    version: str
    capability: str
    split: EvalSplit
    cases: tuple[EvalCase, ...]

    def __post_init__(self) -> None:
        _non_blank("dataset_id", self.dataset_id)
        _non_blank("version", self.version)
        _non_blank("capability", self.capability)
        if not self.cases:
            raise ValueError("evaluation dataset requires at least one case")
        case_ids = tuple(case.case_id for case in self.cases)
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("evaluation dataset case IDs must be unique")

    def snapshot(self) -> JsonObject:
        return {
            "dataset_id": self.dataset_id,
            "version": self.version,
            "capability": self.capability,
            "split": self.split.value,
            "cases": [case.snapshot() for case in self.cases],
        }

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.snapshot())


@dataclass(frozen=True, slots=True)
class EvalDatasetRef:
    dataset_id: str
    version: str
    fingerprint: str

    def __post_init__(self) -> None:
        _non_blank("dataset_id", self.dataset_id)
        _non_blank("version", self.version)
        _non_blank("fingerprint", self.fingerprint)

    @classmethod
    def from_dataset(cls, dataset: EvalDataset) -> EvalDatasetRef:
        return cls(dataset.dataset_id, dataset.version, dataset.fingerprint)


@dataclass(frozen=True, slots=True)
class EvalSubject:
    """Application/configuration being evaluated, independent of the dataset."""

    subject_id: str
    version: str
    configuration: JsonObject

    def __post_init__(self) -> None:
        _non_blank("subject_id", self.subject_id)
        _non_blank("version", self.version)
        canonical_json(self.configuration)

    @property
    def configuration_fingerprint(self) -> str:
        return fingerprint(self.configuration)


@dataclass(frozen=True, slots=True)
class EvalRunProvenance:
    """Reproducibility metadata; not factual evidence for generated content."""

    code_revision: str
    dependency_digest: str
    runtime: JsonObject

    def __post_init__(self) -> None:
        _non_blank("code_revision", self.code_revision)
        _non_blank("dependency_digest", self.dependency_digest)
        canonical_json(self.runtime)


@dataclass(frozen=True, slots=True)
class EvalScore:
    metric: str
    value: float | bool
    source: EvalScoreSource
    evaluator_id: str
    evaluator_version: str
    passed: bool | None = None
    rationale: str | None = None

    def __post_init__(self) -> None:
        _non_blank("metric", self.metric)
        _non_blank("evaluator_id", self.evaluator_id)
        _non_blank("evaluator_version", self.evaluator_version)
        if isinstance(self.value, float) and not math.isfinite(self.value):
            raise ValueError("score value must be finite")
        if self.rationale is not None and not self.rationale.strip():
            raise ValueError("rationale must not be blank when supplied")


@dataclass(frozen=True, slots=True)
class EvalObservation:
    case_id: str
    state: EvalObservationState
    output: JsonObject | None = None
    scores: tuple[EvalScore, ...] = ()
    duration_ms: float | None = None
    error_type: str | None = None

    def __post_init__(self) -> None:
        _non_blank("case_id", self.case_id)
        if self.output is not None:
            canonical_json(self.output)
        if self.duration_ms is not None and self.duration_ms < 0:
            raise ValueError("duration_ms must not be negative")
        if self.state is EvalObservationState.ERROR:
            if self.error_type is None:
                raise ValueError("error observations require error_type")
            _non_blank("error_type", self.error_type)
        elif self.error_type is not None:
            raise ValueError("error_type is only valid for error observations")
        if (
            self.state
            in {
                EvalObservationState.NOT_RUN,
                EvalObservationState.RUNNING,
            }
            and self.scores
        ):
            raise ValueError("non-terminal observations cannot contain scores")


@dataclass(frozen=True, slots=True)
class EvalRun:
    run_id: str
    dataset: EvalDatasetRef
    subject: EvalSubject
    provenance: EvalRunProvenance
    status: EvalRunStatus
    started_at: datetime
    observations: tuple[EvalObservation, ...] = ()
    finished_at: datetime | None = None
    baseline_run_id: str | None = None

    def __post_init__(self) -> None:
        _non_blank("run_id", self.run_id)
        _aware("started_at", self.started_at)
        if self.baseline_run_id is not None:
            _non_blank("baseline_run_id", self.baseline_run_id)
        if self.status is EvalRunStatus.RUNNING:
            if self.finished_at is not None:
                raise ValueError("running evaluation cannot have finished_at")
        else:
            if self.finished_at is None:
                raise ValueError("terminal evaluation run requires finished_at")
            _aware("finished_at", self.finished_at)
            if self.finished_at < self.started_at:
                raise ValueError("finished_at must not precede started_at")


def validate_run_transition(current: EvalRunStatus, target: EvalRunStatus) -> None:
    allowed = {
        EvalRunStatus.RUNNING: {
            EvalRunStatus.COMPLETED,
            EvalRunStatus.INTERRUPTED,
        },
        EvalRunStatus.COMPLETED: set(),
        EvalRunStatus.INTERRUPTED: set(),
    }
    if target not in allowed[current]:
        raise ValueError(f"invalid evaluation run transition: {current} -> {target}")


class Evaluator(Protocol):
    @property
    def evaluator_id(self) -> str: ...

    @property
    def version(self) -> str: ...

    def evaluate(
        self,
        case: EvalCase,
        output: JsonObject,
    ) -> tuple[EvalScore, ...]: ...
