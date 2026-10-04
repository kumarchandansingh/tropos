"""Execute approved scenarios once and persist expected-versus-actual observations."""

from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter

from tropos.core.application.ports.retrieval import KnowledgeChunkRetriever
from tropos.core.application.retrieval.models import KnowledgeSearchRequest
from tropos.core.domain.knowledge_chunk import KnowledgeChunk
from tropos.evals.catalogue import Catalogue, Json, PlannedCase, authorized
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
    results = context.retriever.search(KnowledgeSearchRequest(case.query, case.access, 5))
    hits: list[dict[str, Json]] = []
    relevant_ids = []
    access_ok = current_ok = integrity_ok = True
    for result in results:
        trusted = context.current_chunks.get(result.chunk.chunk_id)
        current = trusted is not None
        allowed = trusted is not None and authorized(trusted.access_policy, case.access)
        intact = trusted == result.chunk
        current_ok &= current
        access_ok &= allowed
        integrity_ok &= intact
        if not (current and allowed and intact):
            hits.append(
                {
                    "rank": result.rank,
                    "redacted": True,
                    "reason": "Returned evidence failed current/access/integrity checks",
                }
            )
            continue
        chunk = result.chunk
        relevant_ids.append(chunk.knowledge_id)
        hits.append(
            {
                "rank": result.rank,
                "redacted": False,
                "chunk_id": chunk.chunk_id,
                "knowledge_id": chunk.knowledge_id,
                "title": chunk.document_title,
                "text": chunk.text,
                "content_fingerprint": chunk.content_fingerprint,
                "canonical_fingerprint": chunk.normalized_content_fingerprint,
                "source_version": chunk.source_version,
                "score": result.score,
                "strategy": result.strategy_version,
            }
        )
    ordered = tuple(dict.fromkeys(relevant_ids))
    expected = set(case.relevant_ids)
    # As in V1, ranks/metrics use unique knowledge IDs within the returned five chunks.
    expectation_ok = expected <= set(ordered[: case.max_rank]) if expected else not results
    ranks_ok = [r.rank for r in results] == list(range(1, len(results) + 1))
    assertions = [
        (
            "expected_evidence",
            expectation_ok,
            f"All expected knowledge in first {case.max_rank} unique results"
            if expected
            else "No evidence should be returned",
        ),
        ("authorized_only", access_ok, "Every returned chunk must be authorized by fixture state"),
        ("current_only", current_ok, "Every returned chunk must belong to the current version"),
        ("evidence_integrity", integrity_ok, "Returned evidence must match the fixture record"),
        (
            "result_contract",
            ranks_ok
            and len(results) <= 5
            and len({r.chunk.chunk_id for r in results}) == len(results)
            and all(r.strategy_version == context.retriever.strategy_version for r in results),
            "At most five unique chunks, consecutive ranks and the declared retrieval strategy",
        ),
    ]
    first_rank = next((i for i, key in enumerate(ordered, 1) if key in expected), None)
    metrics: dict[str, Json] = {
        "label_scope": "knowledge_id",
        "metric_version": "knowledge-v1",
        "cutoff": 5,
        "expected_count": len(expected),
        "returned_chunk_count": len(results),
        "recall_at_1": len(set(ordered[:1]) & expected) / len(expected) if expected else None,
        "recall_at_3": len(set(ordered[:3]) & expected) / len(expected) if expected else None,
        "recall_at_5": len(set(ordered[:5]) & expected) / len(expected) if expected else None,
        "precision_at_5": len(set(ordered[:5]) & expected) / 5 if expected else None,
        "reciprocal_rank": (1 / first_rank if first_rank else 0) if expected else None,
        "no_answer_correct": None if expected else not results,
    }
    metrics["valid_for_quality_metrics"] = all(check[1] for check in assertions[1:])
    if not metrics["valid_for_quality_metrics"]:
        for name in (
            "recall_at_1",
            "recall_at_3",
            "recall_at_5",
            "precision_at_5",
            "reciprocal_rank",
            "no_answer_correct",
        ):
            metrics[name] = None
    return hits, assertions, metrics
