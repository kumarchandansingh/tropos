"""Generic retrieval execution over shared evaluation contracts."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter

from tropos.core.application.ports.retrieval import KnowledgeChunkRetriever
from tropos.core.application.retrieval.models import RetrievalAccessContext
from tropos.core.domain.knowledge_chunk import KnowledgeChunk
from tropos.evals.contracts import (
    EvalApproval,
    EvalCase,
    EvalDataset,
    EvalObservation,
    EvalOrigin,
    EvalObservationState,
    EvalRun,
    EvalScope,
    EvalScore,
    EvalScoreSource,
    EvalSplit,
    JsonObject,
    JsonValue,
)
from tropos.evals.catalogue import Catalogue
from tropos.evals.fixtures import prepare_fixture
from tropos.evals.retrieval_case_evaluation import (
    RetrievalCaseSpec,
    evaluate_retrieval_case,
)

RETRIEVAL_EVALUATOR_ID = "retrieval-deterministic"
RETRIEVAL_EVALUATOR_VERSION = "v2"

RETRIEVAL_HARD_INVARIANTS = (
    "authorized_only",
    "current_only",
    "evidence_integrity",
    "result_contract",
)

RETRIEVAL_DECISION_METRICS = (
    "recall_at_1",
    "recall_at_3",
    "recall_at_5",
    "precision_at_5",
    "reciprocal_rank",
    "no_answer_accuracy",
)


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


def _strings(value: JsonValue) -> tuple[str, ...]:
    result = tuple(_text(item) for item in _array(value))
    if len(result) != len(set(result)):
        raise ValueError("string list must not contain duplicates")
    return result


def _integer(value: JsonValue, *, field: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{field} must be an integer")
    return value


def retrieval_spec_from_eval_case(case: EvalCase) -> RetrievalCaseSpec:
    """Parse the strategy-neutral retrieval contract carried by one EvalCase."""

    inputs = case.inputs
    expected = case.expected
    return RetrievalCaseSpec(
        case_id=case.case_id,
        query=_text(inputs["query"]),
        access=RetrievalAccessContext(
            tenant_id=_text(inputs["tenant_id"]),
            groups=_strings(inputs["groups"]),
        ),
        relevant_knowledge_ids=_strings(expected["relevant_knowledge_ids"]),
        max_rank=_integer(inputs["max_rank"], field="max_rank"),
        tags=case.tags,
    )


class RetrievalExperimentExecutor:
    """Execute retrieval cases through one shared observation/scoring path."""

    def __init__(
        self,
        *,
        retriever: KnowledgeChunkRetriever,
        current_chunks: dict[str, KnowledgeChunk],
        limit: int = 5,
    ) -> None:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        self._retriever = retriever
        self._current_chunks = current_chunks
        self._limit = limit

    def execute(self, case: EvalCase) -> EvalObservation:
        spec = retrieval_spec_from_eval_case(case)
        started = perf_counter()
        evaluation = evaluate_retrieval_case(
            retriever=self._retriever,
            current_chunks=self._current_chunks,
            case=spec,
            limit=self._limit,
        )
        duration_ms = (perf_counter() - started) * 1000

        scores: list[EvalScore] = []
        for name, passed, detail in evaluation.checks:
            scores.append(
                EvalScore(
                    metric=name,
                    value=passed,
                    source=EvalScoreSource.DETERMINISTIC,
                    evaluator_id=RETRIEVAL_EVALUATOR_ID,
                    evaluator_version=RETRIEVAL_EVALUATOR_VERSION,
                    passed=passed,
                    rationale=detail,
                )
            )

        if evaluation.metrics["valid_for_quality_metrics"] is True:
            for metric in (
                "recall_at_1",
                "recall_at_3",
                "recall_at_5",
                "precision_at_5",
                "reciprocal_rank",
            ):
                value = evaluation.metrics[metric]
                if isinstance(value, int | float) and not isinstance(value, bool):
                    scores.append(
                        EvalScore(
                            metric=metric,
                            value=float(value),
                            source=EvalScoreSource.DETERMINISTIC,
                            evaluator_id=RETRIEVAL_EVALUATOR_ID,
                            evaluator_version=RETRIEVAL_EVALUATOR_VERSION,
                        )
                    )

            no_answer = evaluation.metrics["no_answer_correct"]
            if isinstance(no_answer, bool):
                scores.append(
                    EvalScore(
                        metric="no_answer_accuracy",
                        value=1.0 if no_answer else 0.0,
                        source=EvalScoreSource.DETERMINISTIC,
                        evaluator_id=RETRIEVAL_EVALUATOR_ID,
                        evaluator_version=RETRIEVAL_EVALUATOR_VERSION,
                    )
                )

        output: JsonObject = {
            "query": spec.query,
            "tenant_id": spec.access.tenant_id,
            "groups": list(spec.access.groups),
            "expected_knowledge_ids": list(spec.relevant_knowledge_ids),
            "max_rank": spec.max_rank,
            "hits": list(evaluation.hits),
        }
        return EvalObservation(
            case_id=case.case_id,
            state=(
                EvalObservationState.PASSED
                if evaluation.passed
                else EvalObservationState.FAILED
            ),
            output=output,
            scores=tuple(scores),
            duration_ms=duration_ms,
        )



def catalogue_retrieval_dataset(
    catalogue: Catalogue,
    *,
    split: EvalSplit = EvalSplit.DEVELOPMENT,
) -> EvalDataset:
    """Project approved saved-run catalogue cases into the generic dataset model."""

    cases = tuple(
        EvalCase(
            case_id=case.case_id,
            purpose=case.purpose,
            scope=EvalScope.COMPONENT,
            approval=EvalApproval.APPROVED,
            origin=EvalOrigin.SYNTHETIC,
            inputs={
                "query": case.query,
                "tenant_id": case.access.tenant_id,
                "groups": list(case.access.groups),
                "max_rank": case.max_rank,
            },
            expected={"relevant_knowledge_ids": list(case.relevant_ids)},
            tags=case.tags,
        )
        for case in catalogue.cases
        if case.status == "approved"
    )
    return EvalDataset(
        dataset_id=catalogue.dataset_id,
        version=catalogue.version,
        capability="retrieval",
        split=split,
        cases=cases,
    )


class CatalogueRetrievalExperimentExecutor:
    """Run saved catalogue cases through the same generic observation contract."""

    def __init__(self, *, catalogue: Catalogue, directory: Path) -> None:
        self._catalogue = catalogue
        self._directory = directory
        self._by_id = {case.case_id: case for case in catalogue.cases}

    def execute(self, case: EvalCase) -> EvalObservation:
        planned = self._by_id.get(case.case_id)
        if planned is None or planned.status != "approved":
            raise ValueError("generic catalogue run received an unknown or unapproved case")
        context = prepare_fixture(self._catalogue, planned, self._directory)
        return RetrievalExperimentExecutor(
            retriever=context.retriever,
            current_chunks=context.current_chunks,
        ).execute(case)


def hard_invariant_failures(run: EvalRun) -> tuple[tuple[str, str], ...]:
    """Return case/metric pairs for any failed retrieval hard invariant."""

    failures: list[tuple[str, str]] = []
    for observation in run.observations:
        by_metric = {score.metric: score for score in observation.scores}
        for metric in RETRIEVAL_HARD_INVARIANTS:
            score = by_metric.get(metric)
            if score is None or score.passed is not True:
                failures.append((observation.case_id, metric))
    return tuple(failures)
