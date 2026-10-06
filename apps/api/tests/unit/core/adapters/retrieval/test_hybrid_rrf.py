from tropos.core.adapters.retrieval.hybrid_rrf import HybridRrfKnowledgeRetriever
from tropos.core.application.retrieval.models import (
    KnowledgeSearchRequest,
    RetrievalAccessContext,
    RetrievedKnowledgeChunk,
)
from tropos.core.domain.access import AccessPolicy, AccessScope
from tropos.core.domain.knowledge_chunk import KnowledgeChunk


class _FakeRetriever:
    def __init__(
        self,
        *,
        strategy_version: str,
        results: tuple[RetrievedKnowledgeChunk, ...],
    ) -> None:
        self._strategy_version = strategy_version
        self._results = results
        self.requests: list[KnowledgeSearchRequest] = []

    @property
    def strategy_version(self) -> str:
        return self._strategy_version

    def search(self, request: KnowledgeSearchRequest) -> tuple[RetrievedKnowledgeChunk, ...]:
        self.requests.append(request)
        return self._results[: request.limit]


def _chunk(knowledge_id: str) -> KnowledgeChunk:
    text = f"Evidence for {knowledge_id}"
    return KnowledgeChunk(
        chunk_id=f"{knowledge_id}:0",
        knowledge_id=knowledge_id,
        source_system="test",
        source_record_id=f"{knowledge_id}.md",
        source_version="1",
        document_title=knowledge_id,
        sequence_number=0,
        text=text,
        start_offset=0,
        end_offset=len(text),
        content_fingerprint=f"content-{knowledge_id}",
        ingestion_fingerprint=f"ingestion-{knowledge_id}",
        normalized_content_fingerprint=f"normalized-{knowledge_id}",
        normalization_strategy_version="normalize-v1",
        access_policy=AccessPolicy(
            tenant_id="tenant-a",
            scope=AccessScope.TENANT,
        ),
        strategy_version="chunk-v1",
    )


def _result(
    knowledge_id: str,
    *,
    rank: int,
    score: float,
    strategy_version: str,
) -> RetrievedKnowledgeChunk:
    return RetrievedKnowledgeChunk(
        chunk=_chunk(knowledge_id),
        rank=rank,
        score=score,
        strategy_version=strategy_version,
    )


def test_rrf_promotes_evidence_supported_by_both_retrievers() -> None:
    lexical = _FakeRetriever(
        strategy_version="bm25-test",
        results=(
            _result("lexical-only", rank=1, score=12.0, strategy_version="bm25-test"),
            _result("shared", rank=2, score=8.0, strategy_version="bm25-test"),
        ),
    )
    dense = _FakeRetriever(
        strategy_version="dense-test",
        results=(
            _result("dense-only", rank=1, score=0.94, strategy_version="dense-test"),
            _result("shared", rank=2, score=0.89, strategy_version="dense-test"),
        ),
    )

    retriever = HybridRrfKnowledgeRetriever(lexical=lexical, dense=dense)
    results = retriever.search(
        KnowledgeSearchRequest(
            query="find shared evidence",
            access=RetrievalAccessContext(tenant_id="tenant-a"),
            limit=3,
        )
    )

    assert tuple(result.chunk.knowledge_id for result in results) == (
        "shared",
        "dense-only",
        "lexical-only",
    )
    assert results[0].score == 2 * (1 / 62)
    assert all(result.strategy_version.startswith("hybrid-rrf-v1") for result in results)


def test_hybrid_uses_rank_not_incomparable_raw_scores() -> None:
    lexical = _FakeRetriever(
        strategy_version="bm25-test",
        results=(
            _result("lexical", rank=1, score=10_000.0, strategy_version="bm25-test"),
        ),
    )
    dense = _FakeRetriever(
        strategy_version="dense-test",
        results=(
            _result("dense", rank=1, score=0.01, strategy_version="dense-test"),
        ),
    )

    retriever = HybridRrfKnowledgeRetriever(lexical=lexical, dense=dense)
    results = retriever.search(
        KnowledgeSearchRequest(
            query="score scales must not be mixed",
            access=RetrievalAccessContext(tenant_id="tenant-a"),
            limit=2,
        )
    )

    assert results[0].score == results[1].score


def test_hybrid_requests_a_larger_candidate_pool_before_final_trim() -> None:
    lexical = _FakeRetriever(strategy_version="bm25-test", results=())
    dense = _FakeRetriever(strategy_version="dense-test", results=())
    access = RetrievalAccessContext(tenant_id="tenant-a", groups=("support",))

    retriever = HybridRrfKnowledgeRetriever(
        lexical=lexical,
        dense=dense,
        candidate_multiplier=4,
    )
    retriever.search(
        KnowledgeSearchRequest(
            query="bounded candidate generation",
            access=access,
            limit=5,
        )
    )

    assert lexical.requests == [
        KnowledgeSearchRequest(
            query="bounded candidate generation",
            access=access,
            limit=20,
        )
    ]
    assert dense.requests == lexical.requests


def test_candidate_pool_respects_search_contract_maximum() -> None:
    lexical = _FakeRetriever(strategy_version="bm25-test", results=())
    dense = _FakeRetriever(strategy_version="dense-test", results=())

    retriever = HybridRrfKnowledgeRetriever(
        lexical=lexical,
        dense=dense,
        candidate_multiplier=10,
    )
    retriever.search(
        KnowledgeSearchRequest(
            query="large final request",
            access=RetrievalAccessContext(tenant_id="tenant-a"),
            limit=40,
        )
    )

    assert lexical.requests[0].limit == 100
    assert dense.requests[0].limit == 100
