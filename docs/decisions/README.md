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
| [ADR-007](ADR-007-synchronous-ingestion-orchestration-and-sqlite-persistence.md) | Accepted | Coordinate ingestion in one application service and persist durable state through ports, with SQLite as the first adapter |

## Scope

An ADR is appropriate when a choice materially constrains one or more of these areas:

- module or deployment boundaries;
- dependency direction;
- canonical data or evidence identity;
- normalization and version semantics;
- access/security semantics;
- persistence or retrieval strategy;
- external model/provider strategy;
- evaluation and release gates;
- deployment topology or environment promotion.

Routine refactoring, naming changes, and local implementation details do not require ADRs.

Planned technologies are not accepted decisions until the project has enough requirements or implementation evidence to choose them. SQLite is accepted as the initial local persistence adapter, while the production persistence engine, search engine, vector store, model provider, deployment platform, and observability stack remain undecided.

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
