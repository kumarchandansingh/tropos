# Operational Retrieval Strategies V1

Status: Design for implementation  
Scope: promote the already-built BM25, exact dense cosine and hybrid RRF retrievers into the live Resolve runtime without introducing ANN/HNSW.

## 1. User / business problem

Tropos currently exposes only SQLite FTS5/BM25 in the live Resolve path even though the repository already contains governed exact-vector retrieval, persisted embeddings and hybrid Reciprocal Rank Fusion (RRF).

That means retrieval experiments and production-like Resolve behavior are disconnected. A product/quality operator cannot run the same question through BM25, Dense Exact and Hybrid RRF and compare evidence, abstention and latency in the real runtime.

The goal is not to declare hybrid “better.” The goal is to make retrieval strategy an explicit, measurable runtime choice.

## 2. Personas and stories

### Support / Resolve User

- asks a question against governed knowledge;
- gets the same answer/abstention contract regardless of retrieval strategy;
- never receives evidence outside their tenant/group eligibility.

### AI Quality / Product Owner

- selects BM25, Dense Exact or Hybrid RRF;
- compares which chunks/ranks/scores reached the EvidenceSet;
- sees the selected strategy in the trace;
- can repeat the same question across strategies.

### AI / Platform Admin

- configures an embedding provider separately from the LLM provider;
- materializes missing embeddings as derived state;
- can see whether the semantic index is configured and how many current chunks are embedded.

## 3. Analogous products / references

### Weaviate hybrid search

Weaviate runs keyword/BM25 and vector retrieval as separate legs and fuses their outputs rather than treating the raw scores as directly comparable. Tropos keeps its existing RRF design for the same reason: BM25 and cosine scores have different scales.

### Langfuse observability

Langfuse models retrieval/model operations as observations within one request trace. Tropos should continue to expose retrieval strategy, candidate IDs/ranks/scores and downstream model latency in the existing Resolve trace rather than creating a separate diagnostics mechanism.

Reference documentation:
- https://docs.weaviate.io/weaviate/concepts/search/hybrid-search
- https://docs.weaviate.io/weaviate/concepts/search/keyword-search
- https://langfuse.com/docs/observability/overview
- https://langfuse.com/docs/observability/data-model

### Existing Tropos ADR-015

ADR-015 already chose:
- BM25 as explicit lexical baseline;
- embeddings as derived state;
- exact cosine before ANN;
- RRF for hybrid;
- ANN/reranking only after measured need.

This PR operationalizes that accepted architecture rather than replacing it.

## 4. Information architecture

Resolve gains one control:

    Retrieval strategy
    ├── BM25
    ├── Dense exact
    └── Hybrid RRF

Observability / Runtime diagnostics gains:

    Retrieval
    ├── active/request strategy
    ├── embedding provider/model
    ├── embedding strategy version
    ├── embedded current chunk count
    └── materialization readiness

Sources & Ingestion gains a semantic-index action only when an embedding provider is configured:

    Build semantic index

No ANN/index-management screen is added.

## 5. UX flow and states

### BM25

    Ask
    → BM25
    → retrieval gate
    → sufficiency
    → answer / abstain

No embedding configuration is required.

### Dense exact

    Select Dense exact
    → if embedding provider missing:
         inline configuration error
    → if current chunks are missing embeddings:
         explicit semantic-index incomplete error
         → operator runs Build semantic index
    → exact cosine over eligible current chunks
    → retrieval gate
    → sufficiency
    → answer / abstain

### Hybrid RRF

    Select Hybrid RRF
    → ensure embeddings exist
    → BM25 candidate list
    + exact dense candidate list
    → RRF
    → retrieval gate
    → sufficiency
    → answer / abstain

### Failure states

- embedding credentials absent → actionable error; no fallback that silently changes strategy;
- provider call fails → runtime failure with structured error;
- zero embeddings / zero eligible evidence → explicit abstention or configuration error depending on cause;
- BM25 remains available even when embeddings are not configured.

## 6. UI contract

The Resolve strategy selector must make the current strategy visible before the user submits.

Evidence cards show:
- final rank;
- final score;
- retrieval strategy;
- for hybrid: lexical/dense component rank and component score where present.

The UI must not imply fused RRF scores are cosine probabilities or confidence percentages.

## 7. Domain / data-model audit

| Need | Existing concept | Decision |
|---|---|---|
| embedding provider contract | EmbeddingProvider | Reuse |
| derived embedding persistence | SQLiteEmbeddingRepository | Reuse |
| missing embedding materialization | MaterializeEmbeddings | Reuse |
| dense exact retriever | ExactVectorKnowledgeRetriever | Reuse |
| hybrid RRF retriever | HybridRrfKnowledgeRetriever | Reuse |
| BM25 retriever | SQLiteFtsKnowledgeRetriever | Reuse |
| retrieval result | RetrievedKnowledgeChunk | Extend with optional component provenance |
| retrieval configuration | not durable in runtime config | Add typed retrieval strategy enum/settings |
| embedding runtime config | OpenAI adapter exists, env contract absent | Add typed env settings |
| ANN index | absent | Explicitly defer |

Embeddings stay derived state and do not alter canonical knowledge identity.

## 8. Functional architecture

    Runtime request
       ↓
    RetrievalStrategy
       ├── BM25 → SQLite FTS5
       ├── Dense → query embedding → governed eligible embeddings → exact cosine
       └── Hybrid
             ├── BM25 candidates
             ├── Dense candidates
             └── RRF rank fusion
       ↓
    strategy-specific retrieval gate
       ↓
    EvidenceSet
       ↓
    sufficiency
       ↓
    grounded generation

Semantic readiness:

    canonical current chunks
       ↓
    missing_current_chunks(strategy_version)
       ↓
    embedding provider
       ↓
    knowledge_embeddings
       ↓
    exact/hybrid retrieval

## 9. Technical architecture

### Runtime settings

Add typed embedding settings sourced from environment:

- TROPOS_EMBEDDING_PROVIDER (default: openai)
- TROPOS_EMBEDDING_MODEL (default: text-embedding-3-small)
- TROPOS_EMBEDDING_DIMENSIONS (default: 1536)
- TROPOS_OPENAI_API_KEY

Secrets remain repr-hidden and never returned from diagnostics.

### Retrieval strategy

Use typed values:
- bm25
- dense_exact
- hybrid_rrf

BM25 remains the default to preserve current behavior.

### Strategy builder

A shared runtime builder composes:
- SQLiteFtsKnowledgeRetriever;
- optional OpenAIEmbeddingProvider;
- SQLiteEmbeddingRepository;
- ExactVectorKnowledgeRetriever;
- HybridRrfKnowledgeRetriever.

No application/domain layer imports infrastructure adapters.

### Materialization

Expose explicit CLI/UI materialization. Resolve never creates embeddings implicitly: if the semantic index is incomplete, dense/hybrid fail closed with an actionable message.

The materialization operation is idempotent for the current embedding strategy. This avoids surprising provider egress/cost on a question submission.

### Trace

The existing retrieval span records:
- strategy version;
- final chunk IDs/ranks/scores;
- component provenance for hybrid results.

Raw query/evidence content remains absent.

## 10. Security

- ACL/current-version filtering occurs inside SQLiteEmbeddingRepository before cosine ranking.
- Hybrid inherits both governed retrieval legs.
- OpenAI API key is never persisted, traced, returned to browser or included in repr.
- Selecting dense/hybrid without a credential fails closed.
- Embedding text egress uses only already-governed current chunks during materialization; production data-egress policy remains a later platform control before remote enterprise use.

## 11. Observability / evidence

For each Resolve request capture:
- selected/final strategy version;
- result count;
- final ranks/scores;
- hybrid component ranks/scores;
- retrieval gate decision;
- downstream sufficiency/generation latency/tokens.

Runtime diagnostics capture:
- embedding provider/model/configured;
- strategy version if configured;
- persisted embedding count;
- current chunks missing embeddings.

No cost is invented unless provider pricing/usage metadata is actually captured.

## 12. Acceptance evidence

1. BM25 remains default and existing Resolve behavior stays compatible.
2. Dense exact can be selected in CLI and web.
3. Hybrid RRF can be selected in CLI and web.
4. Selecting dense/hybrid without embedding credentials fails with an actionable structured error.
5. Materialization writes only missing derived embeddings and is idempotent.
6. Dense/hybrid never return unauthorized, retired or stale chunks.
7. Hybrid trace/evidence exposes component rank provenance.
8. Runtime diagnostics expose semantic-index readiness without secrets.
9. Same question can be compared across all three strategies.
10. Existing retrieval regression/evaluation gates remain green.
11. No ANN/HNSW or reranker is introduced.

## 13. Deferred / revisit triggers

Defer:
- HNSW / ANN;
- pgvector / managed vector database;
- cross-encoder reranker;
- query rewriting;
- automatic strategy selection;
- weighted raw-score blending.

Revisit ANN when scale rehearsal shows exact cosine violates agreed latency/memory/concurrency thresholds.

Revisit reranking only when production-like labeled evaluation shows a material quality gain over BM25/dense/RRF.
