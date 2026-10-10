# Architecture Decision Records

Architecture Decision Records (ADRs) preserve the context, alternatives, and consequences behind durable technical decisions. Living architecture documents describe the system as it exists; ADRs explain why significant choices were made.

## Index

| ADR | Status | Decision |
| --- | --- | --- |
| [ADR-001](ADR-001-modular-monolith-ports-and-adapters.md) | Accepted | Use a modular monolith with Ports-and-Adapters boundaries |
| [ADR-002](ADR-002-governed-evidence-and-deterministic-chunking.md) | Accepted | Treat `KnowledgeChunk` as governed evidence and establish deterministic lossless chunking before semantic retrieval |
| [ADR-003](ADR-003-protected-main-and-required-ci.md) | Accepted | Protect `main` and require PR-based integration with `api-quality` |
| [ADR-004](ADR-004-deterministic-normalization-and-content-versioning.md) | Accepted | Separate raw/source identity from deterministic canonical content identity |
| [ADR-005](ADR-005-independent-governance-refresh-signal.md) | Accepted | Keep governance refresh independently observable from content/version work |
| [ADR-006](ADR-006-deterministic-format-aware-parsing.md) | Accepted | Route supported source formats through deterministic parsers before canonical normalization |
| [ADR-007](ADR-007-synchronous-ingestion-orchestration-and-sqlite-persistence.md) | Accepted | Use synchronous application orchestration with durable SQLite state as the first ingestion baseline |
| [ADR-008](ADR-008-source-connectors-separate-from-format-parsing.md) | Accepted | Separate source-system acquisition from reusable content-format parsing |
| [ADR-009](ADR-009-explicit-source-failure-taxonomy-and-bounded-retry.md) | Accepted | Classify source failures explicitly and retry only bounded transient failures |
| [ADR-010](ADR-010-governed-sqlite-fts5-retrieval-baseline.md) | Accepted | Use current-version, tenant/group-filtered SQLite FTS5/BM25 as the first retrieval baseline |
| [ADR-011](ADR-011-labeled-retrieval-evaluation-before-semantic-expansion.md) | Accepted | Measure the lexical baseline on a versioned labeled corpus before adding semantic retrieval complexity |
| [ADR-012](ADR-012-versioned-evaluation-catalogues-and-saved-runs.md) | Accepted | Persist immutable versioned retrieval evaluation definitions and saved run evidence |
| [ADR-013](ADR-013-fixed-grounded-knowledge-article-contracts.md) | Accepted | Use fixed evidence-backed Knowledge Article contracts shared across capabilities |
| [ADR-014](ADR-014-vendor-neutral-evaluation-contracts.md) | Accepted | Keep reusable evaluation semantics in Tropos and integrate hosted tools through adapters |
| [ADR-015](ADR-015-evidence-led-dense-and-hybrid-retrieval.md) | Accepted | Evolve retrieval through exact dense search and RRF hybrid before ANN/reranking complexity |
| [ADR-016](ADR-016-stable-evidence-references-with-model-local-aliases.md) | Accepted | Use temporary model aliases that resolve to stable EvidenceRef identities |
| [ADR-017](ADR-017-bounded-business-generation-controls.md) | Accepted | Expose bounded business controls while keeping generation governance system-owned |

## Scope

An ADR is appropriate when a choice materially constrains one or more of these areas:

- module or deployment boundaries;
- dependency direction;
- canonical data or evidence identity;
- normalization and version semantics;
- access/security semantics;
- persistence or retrieval strategy;
- external source/model/provider strategy;
- evaluation and release gates;
- deployment topology or environment promotion.

Routine refactoring, naming changes, and local implementation details do not require ADRs.

Planned technologies are not accepted decisions until the project has enough requirements or implementation evidence to choose them. Lexical retrieval is accepted through ADR-010/011; dense and hybrid evolution through ADR-015; grounded model evidence identity through ADR-016; and bounded business generation control through ADR-017. ANN/vector-serving infrastructure, production database topology, deployment platform, and hosted observability provider remain undecided. SQLite remains the accepted local persistence/search baseline, not a production-scale serving commitment.

## Template

```markdown
# ADR-NNN: Decision title

**Status:** Proposed | Accepted | Superseded
**Date:** YYYY-MM-DD

## Context

Describe the problem, constraints, and decision scope.

## Options considered

1. Option A
2. Option B
3. Option C

## Decision

State the selected option and the reason it was selected.

## Consequences

### Positive

- ...

### Negative / trade-offs

- ...

## Evidence

Link to the implementation, tests, operational controls, or measurements that demonstrate the decision.

## Revisit when

State the conditions that should trigger reconsideration.
```

Accepted ADRs remain part of the decision history. When a decision changes materially, add a superseding ADR or explicitly mark the existing record as superseded rather than removing the historical context.

