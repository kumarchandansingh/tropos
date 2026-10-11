"""Execute approved scenarios once and persist expected-versus-actual observations."""

from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter

from tropos.core.application.ports.retrieval import KnowledgeChunkRetriever
from tropos.core.application.retrieval.models import KnowledgeSearchRequest
from tropos.core.domain.knowledge_chunk import KnowledgeChunk
from tropos.evals.catalogue import Catalogue, Json, PlannedCase
from tropos.evals.retrieval_case_evaluation import (
    RetrievalCaseSpec,
    evaluate_retrieval_case,
)
from tropos.evals.run_store import EvaluationStore


@dataclass(frozen=True)
class EvaluationContext:
    retriever: KnowledgeChunkRetriever
    # Independent fixture oracle: current chunks with authoritative access and content.
    current_chunks: dict[str, KnowledgeChunk]


def execute_catalogue(
    catalogue: Catalogue,
    store: EvaluationStore,
    prepare: Callable[[PlannedCase], EvaluationContext],
    provenance: dict[str, Json],
) -> str:
    for required in ("code_revision", "dependency_digest", "retrieval_strategy", "evaluator"):
        if not provenance.get(required):
            raise ValueError(f"missing run provenance: {required}")
    run_id = store.start(catalogue, provenance)
    try:
        for case in catalogue.cases:
            if case.status != "approved":
                continue
            store.begin_case(run_id, case.case_id)
            started = perf_counter()
            try:
                context = prepare(case)
                if context.retriever.strategy_version != provenance["retrieval_strategy"]:
                    raise ValueError("retriever differs from recorded configuration")
                hits, assertions, metrics = observe(context, case)
            except Exception as exc:
                # Provider/backend messages may contain payloads; preserve only the error class.
                store.record(
                    run_id,
                    case.case_id,
                    "error",
                    (perf_counter() - started) * 1000,
                    [],
                    [],
                    {},
                    type(exc).__name__,
                )
                continue
            store.record(
                run_id,
                case.case_id,
                "passed" if all(a[1] for a in assertions) else "failed",
                (perf_counter() - started) * 1000,
                hits,
                assertions,
                metrics,
            )
    except BaseException:
        store.finish(run_id, interrupted=True)
        raise
    store.finish(run_id)
    return run_id


def observe(
    context: EvaluationContext, case: PlannedCase
) -> tuple[list[dict[str, Json]], list[tuple[str, bool, str]], dict[str, Json]]:
    evaluation = evaluate_retrieval_case(
        retriever=context.retriever,
        current_chunks=context.current_chunks,
        case=RetrievalCaseSpec(
            case_id=case.case_id,
            query=case.query,
            access=case.access,
            relevant_knowledge_ids=case.relevant_ids,
            max_rank=case.max_rank,
            tags=case.tags,
        ),
        limit=5,
    )
    return (
        [dict(hit) for hit in evaluation.hits],
        list(evaluation.checks),
        dict(evaluation.metrics),
    )
