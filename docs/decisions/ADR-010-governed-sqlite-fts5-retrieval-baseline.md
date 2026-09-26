# ADR-010: Establish governed SQLite FTS5 retrieval as the first search baseline

**Status:** Accepted
**Date:** 2026-09-26

## Context

Tropos can already capture, parse, normalize, version, chunk, and persist governed knowledge, but agents and downstream capabilities need a reusable way to retrieve relevant evidence. Introducing embeddings or a vector database before measuring a simpler baseline would add infrastructure and evaluation complexity without evidence that semantic retrieval is required.

Retrieval must also preserve Tropos's governance guarantees. Historical chunks remain in SQLite for lineage, and restricted evidence must never be exposed merely because it matched textually.

## Options considered

1. Start directly with embeddings/vector retrieval.
2. Use application-side substring search over persisted chunks.
3. Use SQLite FTS5 with BM25 ranking and enforce current-version and access constraints in the retrieval SQL.

## Decision

Use SQLite FTS5 with BM25 as the first concrete retrieval adapter.

The reusable core retrieval boundary returns governed `KnowledgeChunk` evidence. Retrieval is strategy-versioned as `sqlite-fts5-bm25-v1`.

The adapter must:

- search persisted chunk title/text through FTS5;
- return only chunks matching the current canonical state in `knowledge_state`;
- require tenant equality;
- enforce restricted-group membership inside the SQL query rather than filtering unauthorized results afterward;
- preserve chunk provenance and access metadata in returned evidence;
- maintain the FTS index as chunks are inserted/deleted/updated;
- expose strategy-native ranking scores without claiming they are normalized probabilities.

The Resolve capability keeps its case-specific retrieval contract. A future adapter may translate a resolved case into the reusable core search request rather than coupling core retrieval to support-case semantics.

## Consequences

### Positive

- Tropos now has an end-to-end deterministic path from governed source capture to retrievable evidence.
- Tenant/group authorization is enforced before evidence leaves the storage/search boundary.
- Historical versions can remain durable without appearing in active retrieval.
- The baseline requires no new runtime dependency or external search service.
- The explicit strategy version gives retrieval evaluations a reproducible behavior identifier.

### Negative / trade-offs

- Lexical retrieval can miss semantically related content that shares few terms with the query.
- The baseline depends on SQLite builds with FTS5 (and JSON table functions for restricted-group checks).
- SQLite FTS5 is a local baseline, not a commitment to the production-scale search topology.
- BM25 scores are strategy-native ranking values and are not directly comparable to future vector or reranker scores.

## Evidence

- `core/application/retrieval/models.py` defines query/access/result contracts.
- `core/application/ports/retrieval.py` defines the reusable retrieval port.
- `core/adapters/retrieval/sqlite_fts.py` implements current-version, tenant/group-filtered FTS5/BM25 retrieval.
- Retrieval tests cover tenant isolation, restricted-group authorization, historical-version exclusion, and index maintenance for newly persisted chunks.

## Revisit when

Revisit the retrieval strategy when labeled retrieval evaluation shows a material semantic-recall gap, when workspace isolation introduces a stronger query partition, or when production scale/availability requirements justify a different search engine.
