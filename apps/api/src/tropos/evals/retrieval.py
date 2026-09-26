from collections.abc import Iterable
from dataclasses import dataclass
from statistics import fmean

from tropos.core.application.ports.retrieval import KnowledgeChunkRetriever
from tropos.core.application.retrieval.models import (
    KnowledgeSearchRequest,
    RetrievalAccessContext,
)


@dataclass(frozen=True, slots=True)
class RetrievalEvalCase:
    """One labeled retrieval query evaluated against knowledge-level relevance labels."""

    case_id: str
    query: str
    access: RetrievalAccessContext
    relevant_knowledge_ids: tuple[str, ...]
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        case_id = self.case_id.strip()
        query = self.query.strip()
        relevant = tuple(value.strip() for value in self.relevant_knowledge_ids)
        tags = tuple(value.strip() for value in self.tags)

        if not case_id:
            raise ValueError("case_id must not be blank")
        if not query:
            raise ValueError("query must not be blank")
        if not isinstance(self.access, RetrievalAccessContext):
            raise TypeError("access must be a RetrievalAccessContext")
        if any(not value for value in relevant):
            raise ValueError("relevant_knowledge_ids must not contain blank values")
        if len(relevant) != len(set(relevant)):
            raise ValueError("relevant_knowledge_ids must not contain duplicates")
        if any(not value for value in tags):
            raise ValueError("tags must not contain blank values")
        if len(tags) != len(set(tags)):
            raise ValueError("tags must not contain duplicates")

        object.__setattr__(self, "case_id", case_id)
        object.__setattr__(self, "query", query)
        object.__setattr__(self, "relevant_knowledge_ids", tuple(sorted(relevant)))
        object.__setattr__(self, "tags", tuple(sorted(tags)))


@dataclass(frozen=True, slots=True)
class RetrievalEvalCaseResult:
    """Deterministic metrics for one labeled retrieval case."""

    case_id: str
    tags: tuple[str, ...]
    retrieved_knowledge_ids: tuple[str, ...]
    recall_at_1: float | None
    recall_at_3: float | None
    recall_at_5: float | None
    precision_at_5: float | None
    reciprocal_rank: float | None
    no_answer_correct: bool | None


@dataclass(frozen=True, slots=True)
class RetrievalEvalReport:
    """Aggregate retrieval-quality report for one versioned retrieval strategy."""

    strategy_version: str
    case_count: int
    answerable_case_count: int
    no_answer_case_count: int
    recall_at_1: float
    recall_at_3: float
    recall_at_5: float
    precision_at_5: float
    mrr: float
    no_answer_accuracy: float | None
    case_results: tuple[RetrievalEvalCaseResult, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "strategy_version": self.strategy_version,
            "case_count": self.case_count,
            "answerable_case_count": self.answerable_case_count,
            "no_answer_case_count": self.no_answer_case_count,
            "recall_at_1": self.recall_at_1,
            "recall_at_3": self.recall_at_3,
            "recall_at_5": self.recall_at_5,
            "precision_at_5": self.precision_at_5,
            "mrr": self.mrr,
            "no_answer_accuracy": self.no_answer_accuracy,
        }


def evaluate_retrieval(
    retriever: KnowledgeChunkRetriever,
    cases: tuple[RetrievalEvalCase, ...],
) -> RetrievalEvalReport:
    """Evaluate one retriever with fixed V1 cutoffs while preserving case-level evidence."""

    if not cases:
        raise ValueError("cases must not be empty")

    results = tuple(_evaluate_case(retriever, case) for case in cases)
    answerable = tuple(result for result in results if result.recall_at_5 is not None)
    no_answer = tuple(result for result in results if result.no_answer_correct is not None)

    return RetrievalEvalReport(
        strategy_version=retriever.strategy_version,
        case_count=len(results),
        answerable_case_count=len(answerable),
        no_answer_case_count=len(no_answer),
        recall_at_1=_mean(result.recall_at_1 for result in answerable),
        recall_at_3=_mean(result.recall_at_3 for result in answerable),
        recall_at_5=_mean(result.recall_at_5 for result in answerable),
        precision_at_5=_mean(result.precision_at_5 for result in answerable),
        mrr=_mean(result.reciprocal_rank for result in answerable),
        no_answer_accuracy=(
            _mean(1.0 if result.no_answer_correct else 0.0 for result in no_answer)
            if no_answer
            else None
        ),
        case_results=results,
    )


def _evaluate_case(
    retriever: KnowledgeChunkRetriever,
    case: RetrievalEvalCase,
) -> RetrievalEvalCaseResult:
    retrieved = retriever.search(
        KnowledgeSearchRequest(
            query=case.query,
            access=case.access,
            limit=5,
        )
    )
    retrieved_ids = tuple(dict.fromkeys(result.chunk.knowledge_id for result in retrieved))
    relevant = set(case.relevant_knowledge_ids)

    if not relevant:
        return RetrievalEvalCaseResult(
            case_id=case.case_id,
            tags=case.tags,
            retrieved_knowledge_ids=retrieved_ids,
            recall_at_1=None,
            recall_at_3=None,
            recall_at_5=None,
            precision_at_5=None,
            reciprocal_rank=None,
            no_answer_correct=not retrieved_ids,
        )

    first_relevant_rank = next(
        (
            rank
            for rank, knowledge_id in enumerate(retrieved_ids, start=1)
            if knowledge_id in relevant
        ),
        None,
    )

    return RetrievalEvalCaseResult(
        case_id=case.case_id,
        tags=case.tags,
        retrieved_knowledge_ids=retrieved_ids,
        recall_at_1=_recall_at(retrieved_ids, relevant, 1),
        recall_at_3=_recall_at(retrieved_ids, relevant, 3),
        recall_at_5=_recall_at(retrieved_ids, relevant, 5),
        precision_at_5=_precision_at(retrieved_ids, relevant, 5),
        reciprocal_rank=0.0 if first_relevant_rank is None else 1.0 / first_relevant_rank,
        no_answer_correct=None,
    )


def _recall_at(retrieved: tuple[str, ...], relevant: set[str], cutoff: int) -> float:
    return len(set(retrieved[:cutoff]) & relevant) / len(relevant)


def _precision_at(retrieved: tuple[str, ...], relevant: set[str], cutoff: int) -> float:
    return len(set(retrieved[:cutoff]) & relevant) / cutoff


def _mean(values: Iterable[float | None]) -> float:
    numeric = tuple(value for value in values if value is not None)
    return fmean(numeric) if numeric else 0.0
