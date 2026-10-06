"""Append-only evaluation definitions and evidence, with explicit run lifecycle."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from tropos.evals.catalogue import Catalogue, Json, canonical
from tropos.evals.reporting import aggregate


class EvaluationStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in {0, 1}:
                raise ValueError("unsupported evaluation database schema")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS eval_datasets (
                    digest TEXT PRIMARY KEY, dataset_id TEXT NOT NULL, version TEXT NOT NULL,
                    corpus_digest TEXT NOT NULL, snapshot TEXT NOT NULL,
                    UNIQUE(dataset_id, version));
                CREATE TABLE IF NOT EXISTS eval_cases (
                    dataset_digest TEXT NOT NULL REFERENCES eval_datasets(digest),
                    case_id TEXT NOT NULL, definition TEXT NOT NULL,
                    PRIMARY KEY(dataset_digest, case_id));
                CREATE TABLE IF NOT EXISTS eval_runs (
                    run_id TEXT PRIMARY KEY, dataset_digest TEXT NOT NULL
                    REFERENCES eval_datasets(digest), provenance TEXT NOT NULL,
                    started TEXT NOT NULL, finished TEXT,
                    status TEXT NOT NULL CHECK(status IN ('running','completed','interrupted')));
                CREATE TABLE IF NOT EXISTS eval_executions (
                    run_id TEXT NOT NULL REFERENCES eval_runs(run_id), case_id TEXT NOT NULL,
                    state TEXT NOT NULL
                        CHECK(state IN ('not_run','running','passed','failed','error')),
                    duration_ms REAL, error TEXT,
                    PRIMARY KEY(run_id,case_id));
                CREATE TABLE IF NOT EXISTS eval_hits (
                    run_id TEXT NOT NULL, case_id TEXT NOT NULL, position INTEGER NOT NULL,
                    evidence TEXT NOT NULL, PRIMARY KEY(run_id,case_id,position),
                    FOREIGN KEY(run_id,case_id) REFERENCES eval_executions(run_id,case_id));
                CREATE TABLE IF NOT EXISTS eval_assertions (
                    run_id TEXT NOT NULL, case_id TEXT NOT NULL, name TEXT NOT NULL,
                    passed INTEGER NOT NULL CHECK(passed IN (0,1)), detail TEXT NOT NULL,
                    PRIMARY KEY(run_id,case_id,name),
                    FOREIGN KEY(run_id,case_id) REFERENCES eval_executions(run_id,case_id));
                CREATE TABLE IF NOT EXISTS eval_metrics (
                    run_id TEXT NOT NULL, case_id TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(run_id,case_id),
                    FOREIGN KEY(run_id,case_id) REFERENCES eval_executions(run_id,case_id));
                PRAGMA user_version = 1;
            """)
            for table in (
                "eval_datasets",
                "eval_cases",
                "eval_hits",
                "eval_assertions",
                "eval_metrics",
            ):
                for operation in ("UPDATE", "DELETE"):
                    db.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_{operation}_immutable
                        BEFORE {operation} ON {table}
                        BEGIN SELECT RAISE(ABORT, 'immutable evaluation record'); END""")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def register(self, catalogue: Catalogue) -> None:
        with self.connect() as db:
            previous = db.execute(
                "SELECT digest FROM eval_datasets WHERE dataset_id=? AND version=?",
                (catalogue.dataset_id, catalogue.version),
            ).fetchone()
            if previous:
                if previous[0] != catalogue.fingerprint:
                    raise ValueError("dataset version already exists with different content")
                return
            db.execute(
                "INSERT INTO eval_datasets VALUES (?,?,?,?,?)",
                (
                    catalogue.fingerprint,
                    catalogue.dataset_id,
                    catalogue.version,
                    catalogue.corpus_fingerprint,
                    catalogue.snapshot,
                ),
            )
            snapshot = json.loads(catalogue.snapshot)
            db.executemany(
                "INSERT INTO eval_cases VALUES (?,?,?)",
                ((catalogue.fingerprint, c["case_id"], canonical(c)) for c in snapshot["cases"]),
            )

    def start(self, catalogue: Catalogue, provenance: dict[str, Json]) -> str:
        self.register(catalogue)
        run_id = uuid4().hex
        with self.connect() as db:
            db.execute(
                "INSERT INTO eval_runs VALUES (?,?,?,?,NULL,'running')",
                (
                    run_id,
                    catalogue.fingerprint,
                    canonical(provenance),
                    datetime.now(UTC).isoformat(),
                ),
            )
            db.executemany(
                "INSERT INTO eval_executions VALUES (?,?,'not_run',NULL,NULL)",
                ((run_id, c.case_id) for c in catalogue.cases),
            )
        return run_id

    def begin_case(self, run_id: str, case_id: str) -> None:
        with self.connect() as db:
            result = db.execute(
                """UPDATE eval_executions SET state='running'
                WHERE run_id=? AND case_id=? AND state='not_run'
                AND EXISTS(SELECT 1 FROM eval_runs WHERE run_id=? AND status='running')""",
                (run_id, case_id, run_id),
            )
            if result.rowcount != 1:
                raise ValueError("case cannot start in its current state")

    def record(
        self,
        run_id: str,
        case_id: str,
        state: str,
        duration_ms: float,
        hits: list[dict[str, Json]],
        assertions: list[tuple[str, bool, str]],
        metrics: dict[str, Json],
        error: str | None = None,
    ) -> None:
        if state not in {"passed", "failed", "error"}:
            raise ValueError("invalid terminal case state")
        with self.connect() as db:
            result = db.execute(
                """UPDATE eval_executions SET state=?,duration_ms=?,error=?
                WHERE run_id=? AND case_id=? AND state='running'
                AND EXISTS(SELECT 1 FROM eval_runs WHERE run_id=? AND status='running')""",
                (state, duration_ms, error, run_id, case_id, run_id),
            )
            if result.rowcount != 1:
                raise ValueError("case result already recorded or run closed")
            db.executemany(
                "INSERT INTO eval_hits VALUES (?,?,?,?)",
                ((run_id, case_id, i, canonical(hit)) for i, hit in enumerate(hits, 1)),
            )
            db.executemany(
                "INSERT INTO eval_assertions VALUES (?,?,?,?,?)",
                ((run_id, case_id, name, passed, detail) for name, passed, detail in assertions),
            )
            db.execute(
                "INSERT INTO eval_metrics VALUES (?,?,?)", (run_id, case_id, canonical(metrics))
            )

    def finish(self, run_id: str, *, interrupted: bool = False) -> None:
        with self.connect() as db:
            result = db.execute(
                """UPDATE eval_runs SET status=?,finished=?
                WHERE run_id=? AND status='running'""",
                (
                    "interrupted" if interrupted else "completed",
                    datetime.now(UTC).isoformat(),
                    run_id,
                ),
            )
            if result.rowcount != 1:
                raise ValueError("run already closed or missing")

    def report(self, run_id: str) -> dict[str, Json]:
        with self.connect() as db:
            run = db.execute("SELECT * FROM eval_runs WHERE run_id=?", (run_id,)).fetchone()
            if not run:
                raise ValueError("run not found")
            dataset = db.execute(
                "SELECT * FROM eval_datasets WHERE digest=?", (run["dataset_digest"],)
            ).fetchone()
            cases: list[Json] = []
            counts = dict.fromkeys(("not_run", "running", "passed", "failed", "error"), 0)
            for execution in db.execute(
                "SELECT * FROM eval_executions WHERE run_id=? ORDER BY case_id", (run_id,)
            ):
                key = (run_id, execution["case_id"])
                definition = db.execute(
                    "SELECT definition FROM eval_cases WHERE dataset_digest=? AND case_id=?",
                    (run["dataset_digest"], execution["case_id"]),
                ).fetchone()
                metric = db.execute(
                    "SELECT payload FROM eval_metrics WHERE run_id=? AND case_id=?", key
                ).fetchone()
                assertions: list[Json] = [
                    {"name": r["name"], "passed": bool(r["passed"]), "detail": r["detail"]}
                    for r in db.execute(
                        "SELECT * FROM eval_assertions WHERE run_id=? AND case_id=? ORDER BY name",
                        key,
                    )
                ]
                hits: list[Json] = [
                    json.loads(r[0])
                    for r in db.execute(
                        "SELECT evidence FROM eval_hits WHERE run_id=? AND case_id=? "
                        "ORDER BY position",
                        key,
                    )
                ]
                cases.append(
                    {
                        "definition": json.loads(definition[0]),
                        "state": execution["state"],
                        "duration_ms": execution["duration_ms"],
                        "error": execution["error"],
                        "actual": hits,
                        "assertions": assertions,
                        "metrics": json.loads(metric[0]) if metric else None,
                    }
                )
                counts[execution["state"]] += 1
            outcome = (
                "failed"
                if counts["failed"] or counts["error"]
                else (
                    "incomplete"
                    if counts["running"] or counts["not_run"] or run["status"] != "completed"
                    else "passed"
                )
            )
            return {
                "schema_version": 1,
                "run_id": run_id,
                "status": run["status"],
                "outcome": outcome,
                "started": run["started"],
                "finished": run["finished"],
                "dataset_id": dataset["dataset_id"],
                "dataset_version": dataset["version"],
                "dataset_digest": dataset["digest"],
                "corpus_digest": dataset["corpus_digest"],
                "provenance": json.loads(run["provenance"]),
                "counts": dict(counts),
                "cases": cases,
                "metrics": aggregate(cases),
            }
