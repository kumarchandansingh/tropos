import gc
import json
import sqlite3
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest

from tropos.core.application.retrieval.models import KnowledgeSearchRequest, RetrievedKnowledgeChunk
from tropos.evals.catalogue import Catalogue, Json, object_value
from tropos.evals.execution import EvaluationContext, execute_catalogue, observe
from tropos.evals.fixtures import prepare_fixture
from tropos.evals.reporting import aggregate, markdown
from tropos.evals.run_store import EvaluationStore

DATASET = Path(__file__).parents[3] / "evals/retrieval/catalogue_v2.json"
PROVENANCE: dict[str, Json] = {
    "code_revision": "synthetic-test",
    "dependency_digest": "test-lock",
    "retrieval_strategy": "sqlite-fts5-bm25-v1",
    "evaluator": "saved-retrieval-v1",
}


def test_real_baseline_persists_failures_draft_and_lifecycle_evidence(tmp_path: Path) -> None:
    catalogue = Catalogue.load(DATASET)
    store = EvaluationStore(tmp_path / "evaluations.sqlite")
    run_id = execute_catalogue(
        catalogue, store, lambda case: prepare_fixture(catalogue, case, tmp_path), PROVENANCE
    )
    report = store.report(run_id)
    assert report["status"] == "completed"
    assert report["outcome"] == "failed"
    assert report["counts"] == {
        "passed": 15,
        "failed": 2,
        "not_run": 1,
        "running": 0,
        "error": 0,
    }
    with store.connect() as db:
        row = db.execute(
            "SELECT state FROM eval_executions WHERE case_id='access-revoked'"
        ).fetchone()
        assert row[0] == "passed"
        row = db.execute(
            "SELECT evidence FROM eval_hits WHERE case_id='freshness-policy-change' AND position=1"
        ).fetchone()
        assert json.loads(row[0])["source_version"] == "2"
    # Reopening the DB preserves every observation; rerunning creates a new run.
    assert EvaluationStore(store.path).report(run_id) == report
    assert "semantic-remote-work" in markdown(report)
    assert "No completed observation" in markdown(report)
    metrics = object_value(report["metrics"])
    assert metrics["excluded_from_metrics"] == 1
    assert metrics["recall_at_5_case_count"] == 12
    assert metrics["recall_at_5"] == pytest.approx(10 / 12)
    assert metrics["no_answer_correct_case_count"] == 5
    assert metrics["no_answer_correct"] == 1.0
    second = store.start(catalogue, PROVENANCE)
    assert second != run_id
    assert store.report(second)["outcome"] == "incomplete"


def test_catalogue_version_is_immutable(tmp_path: Path) -> None:
    catalogue = Catalogue.load(DATASET)
    store = EvaluationStore(tmp_path / "evaluations.sqlite")
    store.register(catalogue)
    store.register(catalogue)
    raw = object_value(json.loads(catalogue.snapshot))
    raw["notes"] = "Changed expectations need a new version"
    with pytest.raises(ValueError, match="different content"):
        store.register(Catalogue.parse(raw))
    with store.connect() as db, pytest.raises(sqlite3.IntegrityError, match="immutable"):
        db.execute("UPDATE eval_cases SET definition='{}'")


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 3),
        ("data_classification", "production"),
        ("split", "ambiguous"),
    ],
)
def test_invalid_catalogue_metadata_rejected(field: str, value: Json) -> None:
    raw = object_value(json.loads(DATASET.read_text()))
    raw[field] = value
    with pytest.raises(ValueError):
        Catalogue.parse(raw)


def test_duplicate_case_and_inaccessible_expectation_rejected() -> None:
    raw = json.loads(DATASET.read_text())
    raw["cases"].append(raw["cases"][0])
    with pytest.raises(ValueError, match="unique case"):
        Catalogue.parse(raw)
    raw = json.loads(DATASET.read_text())
    raw["cases"][0]["tenant_id"] = "other-tenant"
    with pytest.raises(ValueError, match="authorized"):
        Catalogue.parse(raw)


class FakeRetriever:
    strategy_version = "sqlite-fts5-bm25-v1"

    def __init__(self, results: tuple[RetrievedKnowledgeChunk, ...]) -> None:
        self.results = results

    def search(self, request: KnowledgeSearchRequest) -> tuple[RetrievedKnowledgeChunk, ...]:
        return self.results


def test_leaked_evidence_is_blocking_and_redacted(tmp_path: Path) -> None:
    catalogue = Catalogue.load(DATASET)
    case = next(c for c in catalogue.cases if c.case_id == "no-answer-restricted-denied")
    context = prepare_fixture(catalogue, case, tmp_path)
    secret = next(
        c for c in context.current_chunks.values() if c.knowledge_id == "priority-incident"
    )
    result = RetrievedKnowledgeChunk(secret, 1, 1.0, FakeRetriever.strategy_version)
    hits, checks, metrics = observe(
        EvaluationContext(FakeRetriever((result,)), context.current_chunks), case
    )
    assert not dict((name, passed) for name, passed, _ in checks)["authorized_only"]
    assert hits[0]["redacted"] is True
    assert secret.text not in json.dumps(hits)
    assert secret.document_title not in json.dumps(hits)
    assert metrics["recall_at_5"] is None
    assert metrics["valid_for_quality_metrics"] is False


def test_old_version_and_mutated_content_do_not_pass(tmp_path: Path) -> None:
    catalogue = Catalogue.load(DATASET)
    case = next(c for c in catalogue.cases if c.case_id == "freshness-policy-change")
    before = prepare_fixture(catalogue, replace(case, updates=()), tmp_path)
    after = prepare_fixture(catalogue, case, tmp_path)
    old = next(c for c in before.current_chunks.values() if c.knowledge_id == "refund-policy")
    result = RetrievedKnowledgeChunk(old, 1, 1.0, FakeRetriever.strategy_version)
    _, checks, _ = observe(EvaluationContext(FakeRetriever((result,)), after.current_chunks), case)
    assert not dict((name, passed) for name, passed, _ in checks)["current_only"]
    current = next(c for c in after.current_chunks.values() if c.knowledge_id == "refund-policy")
    forged = replace(current, document_title="Invented title")
    result = RetrievedKnowledgeChunk(forged, 1, 1.0, FakeRetriever.strategy_version)
    _, checks, _ = observe(EvaluationContext(FakeRetriever((result,)), after.current_chunks), case)
    assert not dict((name, passed) for name, passed, _ in checks)["evidence_integrity"]


def test_execution_error_is_saved_and_other_cases_continue(tmp_path: Path) -> None:
    catalogue = Catalogue.load(DATASET)
    store = EvaluationStore(tmp_path / "evaluations.sqlite")

    def unavailable(case: object) -> EvaluationContext:
        raise RuntimeError("private backend message")

    run_id = execute_catalogue(catalogue, store, unavailable, PROVENANCE)
    report = store.report(run_id)
    assert object_value(report["counts"])["error"] == 17
    assert report["outcome"] == "failed"
    assert "private backend" not in json.dumps(report)


def test_interruption_preserves_run_without_claiming_success(tmp_path: Path) -> None:
    catalogue = Catalogue.load(DATASET)
    store = EvaluationStore(tmp_path / "evaluations.sqlite")

    def interrupt(case: object) -> EvaluationContext:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        execute_catalogue(catalogue, store, interrupt, PROVENANCE)
    with store.connect() as db:
        run_id = str(db.execute("SELECT run_id FROM eval_runs").fetchone()[0])
    assert store.report(run_id)["status"] == "interrupted"
    assert store.report(run_id)["outcome"] == "incomplete"


def test_terminal_case_cannot_be_overwritten(tmp_path: Path) -> None:
    catalogue = Catalogue.load(DATASET)
    store = EvaluationStore(tmp_path / "evaluations.sqlite")
    run_id = store.start(catalogue, PROVENANCE)
    case_id = catalogue.cases[0].case_id
    store.begin_case(run_id, case_id)
    store.record(run_id, case_id, "error", 0.0, [], [], {}, "RuntimeError")
    with pytest.raises(ValueError, match="already recorded"):
        store.record(run_id, case_id, "passed", 1.0, [], [], {})
    store.finish(run_id, interrupted=True)
    with pytest.raises(ValueError, match="current state"):
        store.begin_case(run_id, catalogue.cases[1].case_id)


def test_empty_or_invalid_quality_observations_are_not_zero_success() -> None:
    summary = aggregate([{"state": "error", "metrics": {}}])
    assert summary["recall_at_5"] is None
    assert summary["recall_at_5_case_count"] == 0
    assert summary["excluded_from_metrics"] == 1


def test_report_command_reads_saved_evidence_without_rerunning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tropos.evals.__main__ import main

    catalogue = Catalogue.load(DATASET)
    store = EvaluationStore(tmp_path / "evaluations.sqlite")
    run_id = store.start(catalogue, PROVENANCE)
    store.finish(run_id, interrupted=True)
    target = tmp_path / "report.md"
    monkeypatch.setattr(
        "sys.argv",
        [
            "evals",
            "report",
            "--database",
            str(store.path),
            "--run-id",
            run_id,
            "--format",
            "markdown",
            "--output",
            str(target),
        ],
    )
    assert main() == 0
    assert "incomplete" in target.read_text()
    assert "No completed observation" in target.read_text()


def test_catalogue_command_has_no_execution_side_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tropos.evals.__main__ import main

    target = tmp_path / "catalogue.md"
    monkeypatch.setattr(
        "sys.argv",
        [
            "evals",
            "catalogue",
            "--dataset",
            str(DATASET),
            "--format",
            "markdown",
            "--output",
            str(target),
        ],
    )
    assert main() == 0
    assert "Not run by this command" in target.read_text()
    assert list(tmp_path.iterdir()) == [target]


def test_run_command_exports_results_and_releases_temporary_databases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tropos.evals.__main__ import main

    definition = json.loads(DATASET.read_text())
    definition["cases"] = [
        case
        for case in definition["cases"]
        if case["case_id"] in {"exact-policy-code", "semantic-remote-work", "planned-delete"}
    ]
    dataset = tmp_path / "catalogue.json"
    dataset.write_text(json.dumps(definition))
    target = tmp_path / "results.json"
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(
        "sys.argv",
        [
            "evals",
            "run",
            "--dataset",
            str(dataset),
            "--database",
            str(tmp_path / "runs.sqlite"),
            "--lockfile",
            str(DATASET.parents[2] / "uv.lock"),
            "--output",
            str(target),
        ],
    )
    # SQLite's transaction context does not close a connection. On Windows,
    # relying on garbage collection leaves temporary database files locked.
    gc_was_enabled = gc.isenabled()
    gc.disable()
    try:
        assert main() == 1  # A saved quality failure, not a command error.
    finally:
        if gc_was_enabled:
            gc.enable()
    result = json.loads(target.read_text())
    assert result["status"] == "completed"
    assert result["counts"] == {
        "passed": 1,
        "failed": 1,
        "not_run": 1,
        "running": 0,
        "error": 0,
    }
    assert not list(tmp_path.glob("tropos-eval-*"))
