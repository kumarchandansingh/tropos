# Tropos learning track

This folder turns Tropos implementation work into reusable engineering understanding.

The learning track is **not** product documentation and does not replace architecture docs or Architecture Decision Records (ADRs). Product docs explain what Tropos is; ADRs explain durable decisions; this folder teaches the engineering concepts behind those decisions and translates them into interview-ready reasoning.

```mermaid
flowchart LR
    P[Real system problem]
    --> F[Failure modes]
    --> I[Invariant]
    --> O[Design options]
    --> T[Trade-offs]
    --> B[Tropos build]
    --> E[Evidence / evaluation]
    --> Q[Interview questions]
```

## Current guides

### [Technical glossary](../GLOSSARY.md)

Use this whenever a document introduces shorthand such as Access Control List (ACL), Approximate Nearest Neighbor (ANN), Reciprocal Rank Fusion (RRF), Mean Reciprocal Rank (MRR), or Hierarchical Navigable Small World (HNSW). Guides should expand technical abbreviations on first use and use the shorthand only after the meaning is established.


### [Enterprise Knowledge Systems — Interview Playbook](ENTERPRISE_KNOWLEDGE_SYSTEMS_INTERVIEW_GUIDE.md)

Use this for:

- hashing, fingerprints, canonicalization, and versioning;
- idempotency, concurrency, ordering, transactions, and consistency;
- parsing, chunking, lexical retrieval, embeddings, and vector indexing;
- access control, enterprise synchronization, retries, checkpoints, and observability;
- retrieval evaluation, migration, scale, and retrieval-augmented generation (RAG) failure modes;
- interview-style questions and sample answers grounded in the Tropos architecture.

### [Dense Retrieval V1 — System Design, Decisions, and Evidence Plan](DENSE_RETRIEVAL_V1.md)

Use this for the semantic-retrieval design exercise and implementation boundary:

- why embeddings are derived from canonical chunks rather than part of canonical identity;
- embedding model/version lineage and idempotent materialization;
- revised/deleted/access-control-changed document behavior;
- governed candidate filtering before similarity ranking;
- exact cosine search before approximate nearest-neighbor (ANN) indexing;
- no-answer trade-offs, hybrid/reranking/Maximum Marginal Relevance (MMR) deferrals, and real-model evaluation evidence.

### [Enterprise Knowledge Systems — Decision & Trade-off Matrix](DECISION_TRADEOFFS.md)

Use this when the interviewer pushes beyond **what did you build?** into:

- what alternatives did you consider?
- why did you select this option at the current scale?
- what did you give up by choosing it?
- what production signal would make you revisit the decision?
- how would the design migrate as scale, reliability, security, or product requirements change?

The matrix covers the current and planned Tropos decisions around identity, idempotency, parsing, canonicalization, hashing, versioning, governance, concurrency, ordering, transactions, chunking, retrieval, authorization, evaluation, vector search, hybrid search, persistence, and enterprise synchronization.

## Working rule for future feature PRs

When a feature introduces a meaningful reusable engineering concept, the same PR should update the relevant learning material with:

1. the concept and vocabulary;
2. the real-world failure mode it solves;
3. the invariant being protected;
4. realistic alternatives considered;
5. the selected decision and why it fits the current constraints;
6. the downside / cost of the choice;
7. the explicit revisit trigger;
8. the Tropos implementation;
9. test/evaluation evidence;
10. interview probes;
11. scale, release, or migration implications.

Do not duplicate implementation reference material here. Link back to architecture docs and ADRs for the authoritative system state.

## Local cleanup and external-operation consistency

The [Katharo learning track](../../katharo/docs/learning/README.md) and [decision matrix](../../katharo/docs/learning/DECISION_TRADEOFFS.md) apply these concepts to exact file identity, document review, stale approvals, quarantine manifests, restore conflicts, and database/filesystem consistency.

## Evaluation evidence

[Evaluation evidence](EVALUATION_EVIDENCE.md) explains versioned test plans, immutable observations, errors versus relevance failures, independent evidence checks and the cost of isolated fixtures.
