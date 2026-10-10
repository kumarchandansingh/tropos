"""SQLite persistence for generic evaluation experiment runs."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import cast

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
    canonical_json,
)


class SQLiteExperimentStore:
    """Persist immutable terminal EvalRun snapshots and per-case observations."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("PRAGMA foreign_keys = ON")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS experiment_runs (
                    run_id TEXT PRIMARY KEY,
                    dataset_id TEXT NOT NULL,
                    dataset_version TEXT NOT NULL,
                    dataset_fingerprint TEXT NOT NULL,
                    subject_json TEXT NOT NULL,
                    provenance_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    baseline_run_id TEXT
                );
                CREATE TABLE IF NOT EXISTS experiment_observations (
                    run_id TEXT NOT NULL REFERENCES experiment_runs(run_id),
                    case_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    output_json TEXT,
                    duration_ms REAL,
                    error_type TEXT,
                    PRIMARY KEY (run_id, case_id)
                );
                CREATE TABLE IF NOT EXISTS experiment_scores (
                    run_id TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    evaluator_id TEXT NOT NULL,
                    evaluator_version TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    source TEXT NOT NULL,
                    passed INTEGER,
                    rationale TEXT,
                    PRIMARY KEY (
                        run_id,
                        case_id,
                        metric,
                        evaluator_id,
                        evaluator_version
                    ),
                    FOREIGN KEY (run_id, case_id)
                    REFERENCES experiment_observations(run_id, case_id)
                );
                """
            )
            for table in (
                "experiment_runs",
                "experiment_observations",
                "experiment_scores",
            ):
                for operation in ("UPDATE", "DELETE"):
                    db.execute(
                        f"""
                        CREATE TRIGGER IF NOT EXISTS {table}_{operation.lower()}_immutable
                        BEFORE {operation} ON {table}
                        BEGIN
                            SELECT RAISE(ABORT, 'immutable experiment record');
                        END
                        """
                    )
            db.commit()

    def save(self, run: EvalRun) -> None:
        if run.status is EvalRunStatus.RUNNING or run.finished_at is None:
            raise ValueError("only terminal evaluation runs can be persisted")

        subject = {
            "subject_id": run.subject.subject_id,
            "version": run.subject.version,
            "configuration": run.subject.configuration,
        }
        provenance = {
            "code_revision": run.provenance.code_revision,
            "dependency_digest": run.provenance.dependency_digest,
            "runtime": run.provenance.runtime,
        }

        with closing(sqlite3.connect(self.path)) as db:
            db.execute("PRAGMA foreign_keys = ON")
            try:
                db.execute(
                    """
                    INSERT INTO experiment_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run.run_id,
                        run.dataset.dataset_id,
                        run.dataset.version,
                        run.dataset.fingerprint,
                        canonical_json(subject),
                        canonical_json(provenance),
                        run.status.value,
                        run.started_at.isoformat(),
                        run.finished_at.isoformat(),
                        run.baseline_run_id,
                    ),
                )
                for observation in run.observations:
                    db.execute(
                        """
                        INSERT INTO experiment_observations
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run.run_id,
                            observation.case_id,
                            observation.state.value,
                            None
                            if observation.output is None
                            else canonical_json(observation.output),
                            observation.duration_ms,
                            observation.error_type,
                        ),
                    )
                    for score in observation.scores:
                        db.execute(
                            """
                            INSERT INTO experiment_scores
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                run.run_id,
                                observation.case_id,
                                score.metric,
                                score.evaluator_id,
                                score.evaluator_version,
                                canonical_json(score.value),
                                score.source.value,
                                None if score.passed is None else int(score.passed),
                                score.rationale,
                            ),
                        )
                db.commit()
            except sqlite3.IntegrityError as exc:
                raise ValueError("experiment run already exists or is inconsistent") from exc

    def load(self, run_id: str) -> EvalRun:
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys = ON")
            run_row = db.execute(
                "SELECT * FROM experiment_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if run_row is None:
                raise ValueError("experiment run not found")

            subject_raw = cast(JsonObject, json.loads(run_row["subject_json"]))
            provenance_raw = cast(JsonObject, json.loads(run_row["provenance_json"]))
            observations: list[EvalObservation] = []

            observation_rows = db.execute(
                """
                SELECT * FROM experiment_observations
                WHERE run_id=?
                ORDER BY case_id
                """,
                (run_id,),
            ).fetchall()
            for observation_row in observation_rows:
                scores: list[EvalScore] = []
                for score_row in db.execute(
                    """
                    SELECT * FROM experiment_scores
                    WHERE run_id=? AND case_id=?
                    ORDER BY metric, evaluator_id, evaluator_version
                    """,
                    (run_id, observation_row["case_id"]),
                ):
                    scores.append(
                        EvalScore(
                            metric=score_row["metric"],
                            value=_score_value(json.loads(score_row["value_json"])),
                            source=EvalScoreSource(score_row["source"]),
                            evaluator_id=score_row["evaluator_id"],
                            evaluator_version=score_row["evaluator_version"],
                            passed=(
                                None if score_row["passed"] is None else bool(score_row["passed"])
                            ),
                            rationale=score_row["rationale"],
                        )
                    )

                output = (
                    None
                    if observation_row["output_json"] is None
                    else cast(JsonObject, json.loads(observation_row["output_json"]))
                )
                observations.append(
                    EvalObservation(
                        case_id=observation_row["case_id"],
                        state=EvalObservationState(observation_row["state"]),
                        output=output,
                        scores=tuple(scores),
                        duration_ms=observation_row["duration_ms"],
                        error_type=observation_row["error_type"],
                    )
                )

            return EvalRun(
                run_id=run_row["run_id"],
                dataset=EvalDatasetRef(
                    dataset_id=run_row["dataset_id"],
                    version=run_row["dataset_version"],
                    fingerprint=run_row["dataset_fingerprint"],
                ),
                subject=EvalSubject(
                    subject_id=_required_text(subject_raw, "subject_id"),
                    version=_required_text(subject_raw, "version"),
                    configuration=_required_object(subject_raw, "configuration"),
                ),
                provenance=EvalRunProvenance(
                    code_revision=_required_text(provenance_raw, "code_revision"),
                    dependency_digest=_required_text(
                        provenance_raw,
                        "dependency_digest",
                    ),
                    runtime=_required_object(provenance_raw, "runtime"),
                ),
                status=EvalRunStatus(run_row["status"]),
                started_at=_parse_datetime(run_row["started_at"]),
                observations=tuple(observations),
                finished_at=_parse_datetime(run_row["finished_at"]),
                baseline_run_id=run_row["baseline_run_id"],
            )


def _score_value(value: object) -> float | bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    raise ValueError("persisted score must be numeric or boolean")


def _required_text(payload: JsonObject, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"persisted {key} must be non-empty text")
    return value


def _required_object(payload: JsonObject, key: str) -> JsonObject:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"persisted {key} must be an object")
    return value


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)
