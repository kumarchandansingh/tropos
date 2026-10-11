"""Shared retrieval case evaluation used by all retrieval experiment paths."""

from __future__ import annotations

from dataclasses import dataclass

from tropos.core.application.ports.retrieval import KnowledgeChunkRetriever
from tropos.core.application.retrieval.models import (
    KnowledgeSearchRequest,
    RetrievalAccessContext,
)
from tropos.core.domain.access import AccessScope
from tropos.core.domain.knowledge_chunk import KnowledgeChunk
from tropos.evals.contracts import JsonObject


@dataclass(frozen=True, slots=True)
class RetrievalCaseSpec:
    """Strategy-neutral retrieval expectation for one evaluation case."""

    case_id: str
    query: str
    access: RetrievalAccessContext
    relevant_knowledge_ids: tuple[str, ...]
    max_rank: int = 5
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("case_id must not be blank")
        if not self.query.strip():
            raise ValueError("query must not be blank")
        if not 1 <= self.max_rank <= 5:
            raise ValueError("max_rank must be between 1 and 5")
        if len(self.relevant_knowledge_ids) != len(set(self.relevant_knowledge_ids)):
            raise ValueError("relevant_knowledge_ids must not contain duplicates")
        if any(not item.strip() for item in self.relevant_knowledge_ids):
            raise ValueError("relevant_knowledge_ids must not contain blanks")
        if len(self.tags) != len(set(self.tags)):
            raise ValueError("tags must not contain duplicates")
        if any(not tag.strip() for tag in self.tags):
            raise ValueError("tags must not contain blanks")


@dataclass(frozen=True, slots=True)
class RetrievalCaseEvaluation:
    """Safe observable output, deterministic checks, and quality metrics."""

    hits: tuple[JsonObject, ...]
    checks: tuple[tuple[str, bool, str], ...]
    metrics: JsonObject

    @property
    def passed(self) -> bool:
        return all(check[1] for check in self.checks)


def is_authorized(chunk: KnowledgeChunk, access: RetrievalAccessContext) -> bool:
    policy = chunk.access_policy
    return policy.tenant_id == access.tenant_id and (
        policy.scope is AccessScope.TENANT
        or policy.scope is AccessScope.RESTRICTED
        and bool(set(policy.allowed_groups) & set(access.groups))
    )


def evaluate_retrieval_case(
    *,
    retriever: KnowledgeChunkRetriever,
    current_chunks: dict[str, KnowledgeChunk],
    case: RetrievalCaseSpec,
    limit: int = 5,
) -> RetrievalCaseEvaluation:
    """Evaluate one retriever against one case with shared assurance semantics."""

    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")

    results = retriever.search(
        KnowledgeSearchRequest(
            query=case.query,
            access=case.access,
            limit=limit,
        )
    )

    hits: list[JsonObject] = []
    relevant_ids: list[str] = []
    access_ok = True
    current_ok = True
    integrity_ok = True

    for result in results:
        trusted = current_chunks.get(result.chunk.chunk_id)
        current = trusted is not None
        allowed = trusted is not None and is_authorized(trusted, case.access)
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
    expected = set(case.relevant_knowledge_ids)
    expectation_ok = expected <= set(ordered[: case.max_rank]) if expected else not results
    ranks_ok = [result.rank for result in results] == list(range(1, len(results) + 1))
    checks = (
        (
            "expected_evidence",
            expectation_ok,
            (
                f"All expected knowledge in first {case.max_rank} unique results"
                if expected
                else "No evidence should be returned"
            ),
        ),
        (
            "authorized_only",
            access_ok,
            "Every returned chunk must be authorized by fixture state",
        ),
        (
            "current_only",
            current_ok,
            "Every returned chunk must belong to the current version",
        ),
        (
            "evidence_integrity",
            integrity_ok,
            "Returned evidence must match the fixture record",
        ),
        (
            "result_contract",
            ranks_ok
            and len(results) <= limit
            and len({result.chunk.chunk_id for result in results}) == len(results)
            and all(result.strategy_version == retriever.strategy_version for result in results),
            (
                f"At most {limit} unique chunks, consecutive ranks and the "
                "declared retrieval strategy"
            ),
        ),
    )

    first_rank = next(
        (index for index, key in enumerate(ordered, 1) if key in expected),
        None,
    )
    metrics: JsonObject = {
        "label_scope": "knowledge_id",
        "metric_version": "knowledge-v1",
        "cutoff": limit,
        "expected_count": len(expected),
        "returned_chunk_count": len(results),
        "recall_at_1": (len(set(ordered[:1]) & expected) / len(expected) if expected else None),
        "recall_at_3": (len(set(ordered[:3]) & expected) / len(expected) if expected else None),
        "recall_at_5": (len(set(ordered[:5]) & expected) / len(expected) if expected else None),
        "precision_at_5": (len(set(ordered[:5]) & expected) / 5 if expected else None),
        "reciprocal_rank": ((1 / first_rank if first_rank else 0) if expected else None),
        "no_answer_correct": None if expected else not results,
    }

    hard_invariants_passed = all(
        passed for name, passed, _ in checks if name != "expected_evidence"
    )
    metrics["valid_for_quality_metrics"] = hard_invariants_passed
    if not hard_invariants_passed:
        for name in (
            "recall_at_1",
            "recall_at_3",
            "recall_at_5",
            "precision_at_5",
            "reciprocal_rank",
            "no_answer_correct",
        ):
            metrics[name] = None

    return RetrievalCaseEvaluation(
        hits=tuple(hits),
        checks=checks,
        metrics=metrics,
    )
