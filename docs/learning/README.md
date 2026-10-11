# Engineering deep dives

## Purpose

This folder explains selected Tropos mechanisms in more depth than the living architecture requires. The notes connect a measured system problem to the design options, trade-offs, implementation boundary, and evidence used to evaluate the decision.

These notes are public engineering material. They are not authoritative for implementation status; product and architecture documents remain the source of truth for the current system.

## Current deep dives

### [Dense Retrieval V1](DENSE_RETRIEVAL_V1.md)

Explains:

- why embeddings are derived state rather than canonical knowledge;
- embedding model/version lineage and idempotent materialization;
- revised, deleted, and access-control-changed document behavior;
- governed candidate filtering before similarity ranking;
- exact cosine search before approximate nearest-neighbor (ANN) indexing;
- measured no-answer behavior and the evidence required before adding more retrieval complexity.

### [Hybrid Retrieval V1](HYBRID_RETRIEVAL_V1.md)

Explains:

- lexical BM25 and dense semantic retrieval as complementary rankers;
- Reciprocal Rank Fusion (RRF);
- candidate-depth and fusion trade-offs;
- the boundary between ranking and abstention;
- evidence required before adding reranking or approximate vector search.

### [Evaluation evidence](EVALUATION_EVIDENCE.md)

Explains the current retrieval evidence, limitations of the synthetic corpus, and how evaluation evidence informs subsequent design work.

### [Engineering decision register](DECISION_TRADEOFFS.md)

Summarizes important design choices across identity, versioning, governance, concurrency, chunking, retrieval, evaluation, persistence, and synchronization. Durable architecture decisions remain canonical in the Architecture Decision Record index.

## Working rule

A deep dive is appropriate when a mechanism benefits from more explanation than the living architecture should carry. It should answer:

1. What system problem motivated the mechanism?
2. What constraints and quality attributes matter?
3. Which credible options exist?
4. What did Tropos choose at the current scale?
5. What does that choice give up?
6. What evidence supports the choice?
7. What would trigger a different design?

A feature is not complete merely because a deep dive exists. Material changes must also update the authoritative product, architecture, quality, delivery, or decision documentation identified in the [public documentation standard](../standards/PUBLIC_DOCUMENTATION_STANDARD.md).
