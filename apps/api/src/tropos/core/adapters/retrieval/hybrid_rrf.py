from dataclasses import dataclass

from tropos.core.application.ports.retrieval import KnowledgeChunkRetriever
from tropos.core.application.retrieval.models import (
    KnowledgeSearchRequest,
    RetrievedKnowledgeChunk,
)
from tropos.core.domain.knowledge_chunk import KnowledgeChunk

_STRATEGY_VERSION = "hybrid-rrf-v1"


@dataclass(slots=True)
class _FusionCandidate:
    chunk: KnowledgeChunk
    score: float
    best_rank: int


class HybridRrfKnowledgeRetriever:
    """Fuse governed lexical and dense rankings using Reciprocal Rank Fusion."""

    def __init__(
        self,
        *,
        lexical: KnowledgeChunkRetriever,
        dense: KnowledgeChunkRetriever,
        rrf_k: int = 60,
        candidate_multiplier: int = 4,
    ) -> None:
        if rrf_k < 1:
            raise ValueError("rrf_k must be at least 1")
        if candidate_multiplier < 1:
            raise ValueError("candidate_multiplier must be at least 1")
        self._lexical = lexical
        self._dense = dense
        self._rrf_k = rrf_k
        self._candidate_multiplier = candidate_multiplier

    @property
    def strategy_version(self) -> str:
        return (
            f"{_STRATEGY_VERSION}:k={self._rrf_k}:"
            f"{self._lexical.strategy_version}+{self._dense.strategy_version}"
        )

    def search(self, request: KnowledgeSearchRequest) -> tuple[RetrievedKnowledgeChunk, ...]:
        if not isinstance(request, KnowledgeSearchRequest):
            raise TypeError("request must be a KnowledgeSearchRequest")

        candidate_limit = min(
            100,
            max(request.limit, request.limit * self._candidate_multiplier),
        )
        candidate_request = KnowledgeSearchRequest(
            query=request.query,
            access=request.access,
            limit=candidate_limit,
        )

        rankings = (
            self._lexical.search(candidate_request),
            self._dense.search(candidate_request),
        )

        fused: dict[str, _FusionCandidate] = {}
        for ranking in rankings:
            for result in ranking:
                chunk_id = result.chunk.chunk_id
                contribution = 1.0 / (self._rrf_k + result.rank)
                existing = fused.get(chunk_id)
                if existing is None:
                    fused[chunk_id] = _FusionCandidate(
                        chunk=result.chunk,
                        score=contribution,
                        best_rank=result.rank,
                    )
                    continue

                existing.score += contribution
                existing.best_rank = min(existing.best_rank, result.rank)

        ordered = sorted(
            fused.values(),
            key=lambda candidate: (
                -candidate.score,
                candidate.best_rank,
                candidate.chunk.knowledge_id,
                candidate.chunk.sequence_number,
                candidate.chunk.chunk_id,
            ),
        )[: request.limit]

        return tuple(
            RetrievedKnowledgeChunk(
                chunk=candidate.chunk,
                rank=rank,
                score=candidate.score,
                strategy_version=self.strategy_version,
            )
            for rank, candidate in enumerate(ordered, start=1)
        )
