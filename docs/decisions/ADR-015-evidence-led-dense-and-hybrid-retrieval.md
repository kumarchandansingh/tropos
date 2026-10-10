# ADR-015: evidence-led dense and hybrid retrieval evolution

**Status:** Accepted  
**Date:** 2026-10-10

## Context

The lexical SQLite FTS5/BM25 baseline performed well for exact terms, identifiers and policy language but the labeled retrieval set exposed semantic/paraphrase misses. Tropos needed to add semantic retrieval without prematurely replacing lexical retrieval or introducing Approximate Nearest Neighbor (ANN) infrastructure before representation quality was understood.

## Options considered

1. Keep BM25 only.
2. Replace BM25 with vector retrieval.
3. Add an exact dense retriever behind the shared retrieval contract, compare it with BM25, then add hybrid rank fusion if the strategies are complementary.
4. Move immediately to HNSW/managed vector infrastructure and reranking.

## Decision

Adopt an additive retrieval evolution:

- keep BM25 as an explicit lexical strategy;
- materialize embeddings as derived state outside the canonical knowledge transaction;
- use exact cosine similarity for Dense V1;
- keep authorization/current-version guarantees at the governed retrieval boundary;
- combine lexical and dense results with Reciprocal Rank Fusion (RRF) when measured evidence supports complementary strengths;
- defer ANN/HNSW, weighted raw-score blending, and cross-encoder reranking until scale/quality evidence justifies them.

## Why

Exact dense search isolates semantic representation quality from ANN approximation and vector-index operations. RRF combines rank positions without assuming BM25 and cosine scores share the same numerical meaning. Retaining lexical retrieval preserves strong identifier/exact-term behavior.

## Consequences

### Positive

- retrieval strategies remain comparable behind one contract;
- semantic recall can improve without discarding lexical strengths;
- exact dense results provide a clean quality baseline;
- RRF avoids uncalibrated score blending;
- ANN/reranking complexity is postponed until evidence supports it.

### Negative / trade-offs

- exact dense scan is O(N) and not the final topology for very large corpora;
- embeddings add model lifecycle, storage and re-materialization concerns;
- hybrid retrieval operates two retrieval paths;
- RRF has candidate-depth/fusion parameters that still need evaluation.

## Evidence

- PR #25: Dense Retrieval V1
- PR #26: dense retrieval evidence
- PR #29: RRF hybrid retrieval
- PR #30: BM25/dense/hybrid comparison
- `docs/learning/DENSE_RETRIEVAL_V1.md`
- `docs/learning/HYBRID_RETRIEVAL_V1.md`
- `apps/api/src/tropos/core/adapters/retrieval/exact_vector.py`
- `apps/api/src/tropos/core/adapters/retrieval/hybrid_rrf.py`

## Revisit when

- corpus size or p95 latency makes exact scan materially slow;
- production-like evaluation shows a calibrated reranker materially improves relevance;
- model/provider migration requires a new embedding strategy;
- hybrid retrieval regresses critical exact-term or no-answer scenarios;
- operational scale requires a dedicated vector/search service.
