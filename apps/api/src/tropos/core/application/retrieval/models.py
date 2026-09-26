from dataclasses import dataclass
from math import isfinite

from tropos.core.domain.knowledge_chunk import KnowledgeChunk


@dataclass(frozen=True, slots=True)
class RetrievalAccessContext:
    """Tenant and group context used to authorize retrieval inside the search boundary."""

    tenant_id: str
    groups: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        tenant_id = self.tenant_id.strip()
        if not tenant_id:
            raise ValueError("tenant_id must not be blank")

        groups = tuple(group.strip() for group in self.groups)
        if any(not group for group in groups):
            raise ValueError("groups must not contain blank values")
        if len(groups) != len(set(groups)):
            raise ValueError("groups must not contain duplicates")

        object.__setattr__(self, "tenant_id", tenant_id)
        object.__setattr__(self, "groups", tuple(sorted(groups)))


@dataclass(frozen=True, slots=True)
class KnowledgeSearchRequest:
    """One authorized lexical retrieval request."""

    query: str
    access: RetrievalAccessContext
    limit: int = 5

    def __post_init__(self) -> None:
        query = self.query.strip()
        if not query:
            raise ValueError("query must not be blank")
        if not isinstance(self.access, RetrievalAccessContext):
            raise TypeError("access must be a RetrievalAccessContext")
        if not 1 <= self.limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        object.__setattr__(self, "query", query)


@dataclass(frozen=True, slots=True)
class RetrievedKnowledgeChunk:
    """One authorized evidence chunk returned by a versioned retrieval strategy."""

    chunk: KnowledgeChunk
    rank: int
    score: float
    strategy_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.chunk, KnowledgeChunk):
            raise TypeError("chunk must be a KnowledgeChunk")
        if self.rank < 1:
            raise ValueError("rank must be at least 1")
        if not isfinite(self.score):
            raise ValueError("score must be finite")
        if not self.strategy_version.strip():
            raise ValueError("strategy_version must not be blank")
