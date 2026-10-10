from __future__ import annotations

from tropos.evals.contracts import JsonObject
from tropos.evals.regression_gate import compare_retrieval_reports


def _assertions(expected: bool = True, *, authorized: bool = True) -> list[JsonObject]:
    values = {
        "expected_evidence": expected,
        "authorized_only": authorized,
        "current_only": True,
        "evidence_integrity": True,
        "result_contract": True,
    }
    return [
        {"name": name, "passed": passed, "detail": f"{name} fixture"}
        for name, passed in values.items()
    ]


def _report(
    revision: str,
    *,
    answerable_quality: float,
    answerable_passed: bool,
    no_answer_correct: bool = True,
    authorized: bool = True,
) -> JsonObject:
    return {
        "schema_version": 1,
        "run_id": f"run-{revision}",
        "status": "completed",
        "outcome": "passed" if answerable_passed and authorized else "failed",
        "started": "2026-10-10T12:00:00+00:00",
        "finished": "2026-10-10T12:00:01+00:00",
        "dataset_id": "retrieval-fixture",
        "dataset_version": "v1",
        "dataset_digest": "same-dataset-fingerprint",
        "corpus_digest": "same-corpus-fingerprint",
        "provenance": {
            "code_revision": revision,
            "dependency_digest": f"lock-{revision}",
            "python_version": "3.14",
            "evaluator": "saved-retrieval-v1",
            "retrieval_strategy": "sqlite-fts5-bm25-v1",
            "max_characters": 2000,
            "gate_policy": "all-expectations-and-invariants-v1",
            "limit": 5,
            "working_tree_dirty": False,
        },
        "counts": {
            "not_run": 0,
            "running": 0,
            "passed": 2 if answerable_passed else 1,
            "failed": 0 if answerable_passed else 1,
            "error": 0,
        },
        "cases": [
            {
                "definition": {"case_id": "answerable", "tags": ["answerable"]},
                "state": "passed" if answerable_passed else "failed",
                "duration_ms": 1.0,
                "error": None,
                "actual": [],
                "assertions": _assertions(answerable_passed, authorized=authorized),
                "metrics": {
                    "metric_version": "knowledge-v1",
                    "recall_at_1": answerable_quality,
                    "recall_at_3": answerable_quality,
                    "recall_at_5": answerable_quality,
                    "precision_at_5": answerable_quality,
                    "reciprocal_rank": answerable_quality,
                    "no_answer_correct": None,
                    "valid_for_quality_metrics": authorized,
                },
            },
            {
                "definition": {"case_id": "no-answer", "tags": ["no-answer"]},
                "state": "passed",
                "duration_ms": 1.0,
                "error": None,
                "actual": [],
                "assertions": _assertions(True),
                "metrics": {
                    "metric_version": "knowledge-v1",
                    "recall_at_1": None,
                    "recall_at_3": None,
                    "recall_at_5": None,
                    "precision_at_5": None,
                    "reciprocal_rank": None,
                    "no_answer_correct": no_answer_correct,
                    "valid_for_quality_metrics": True,
                },
            },
        ],
        "metrics": {},
    }


def test_known_case_and_metric_regression_fail_the_gate() -> None:
    decision = compare_retrieval_reports(
        _report("base", answerable_quality=1.0, answerable_passed=True),
        _report("head", answerable_quality=0.0, answerable_passed=False),
    )

    assert decision.passed is False
    assert decision.case_regressions == ("answerable",)
    recall = next(
        result
        for result in decision.comparison.gate_results
        if result.metric == "recall_at_5"
    )
    assert recall.passed is False


def test_legitimate_improvement_is_not_blocked_by_an_old_exact_aggregate() -> None:
    decision = compare_retrieval_reports(
        _report("base", answerable_quality=0.0, answerable_passed=False),
        _report("head", answerable_quality=1.0, answerable_passed=True),
    )

    assert decision.passed is True
    assert decision.case_regressions == ()
    assert decision.comparison.improvements[0].case_id == "answerable"


def test_hard_invariant_blocks_candidate_even_when_quality_improves() -> None:
    decision = compare_retrieval_reports(
        _report("base", answerable_quality=0.0, answerable_passed=False),
        _report(
            "head",
            answerable_quality=1.0,
            answerable_passed=True,
            authorized=False,
        ),
    )

    assert decision.passed is False
    authorized = next(
        result
        for result in decision.comparison.gate_results
        if result.metric == "authorized_only"
    )
    assert authorized.passed is False
