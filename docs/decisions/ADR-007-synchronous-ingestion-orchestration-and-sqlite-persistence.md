# ADR-007: Synchronous ingestion orchestration and SQLite persistence

**Status:** Accepted  
**Date:** 2026-09-26

## Context

Tropos already has deterministic parsing, normalization, canonical version resolution, and chunking. Those components need an application workflow that coordinates them against durable prior state without collapsing their implementation logic into one class.

Version resolution also depends on persisted canonical state. Exact source captures, workflow outcomes, knowledge versions, chunks, and governance state need a durable baseline before retrieval can be implemented.

The current system is a modular monolith. Introducing a message broker, workflow engine, independent worker services, or saga compensation would add distributed-systems complexity before there is a workload that requires it.

## Options considered

1. Split ingestion steps into asynchronous worker services coordinated through a broker or workflow engine.
2. Let each ingestion component call the next component and persistence directly.
3. Use one synchronous application orchestrator over explicit ports, with one transactional SQLite adapter as the first durable implementation.

## Decision

Tropos will use `IngestKnowledge` as the ingestion application orchestrator.

The orchestrator owns workflow order and branching only. Parser, normalizer, version resolver, chunker, source capture, workflow state, and canonical persistence keep their own responsibilities behind contracts.

The initial persistence boundary is separated into source capture, canonical knowledge state, and ingestion-run responsibilities. A single `SQLiteIngestionStore` implements those ports for the first local durable baseline.

The workflow persists exact source evidence, records workflow stage and failure information, loads previous canonical state, resolves content and governance work independently, chunks only when a new version is required, and atomically commits a new document version, chunks, and current-state pointer.

Duplicate completed source captures are idempotent: the prior result is returned as a replay. Version and governance writes compare the state observed by the orchestrator with the state still present at commit time; conflicting concurrent changes fail explicitly rather than silently overwriting newer state.

Governance refresh remains independent of content processing. When access and content change together, the currently persisted version receives the new governance state before the new content version is committed.

## Consequences

### Positive

- ingestion has one explicit, auditable execution path;
- the orchestrator coordinates steps without owning parser, chunker, SQL, or fingerprint logic;
- canonical version decisions can use durable previous state;
- raw captures and failed workflow stages are retained for replay and diagnosis;
- duplicate completed captures are idempotent;
- canonical version and chunk writes are atomic within SQLite;
- stale concurrent writes are surfaced through expected-state checks;
- persistence can be replaced behind application ports without rewriting ingestion logic.

### Negative / trade-offs

- orchestration is synchronous and does not yet provide automatic retry/backoff;
- an in-progress duplicate request is rejected rather than joined to the existing run;
- SQLite is a local baseline, not a production-scale persistence commitment;
- governance refresh and subsequent new-version creation are two transactions, so a failure between them can leave the old content correctly restricted while the new content version remains uncommitted;
- there is no queue, worker recovery loop, or distributed compensation mechanism.

## Evidence

- `apps/api/src/tropos/core/application/ingestion/ingest_knowledge.py`
- `apps/api/src/tropos/core/application/ingestion/run_state.py`
- `apps/api/src/tropos/core/application/ports/persistence.py`
- `apps/api/src/tropos/core/adapters/persistence/sqlite.py`
- `apps/api/tests/unit/core/adapters/persistence/test_sqlite_ingestion.py`

## Revisit when

Revisit this decision when ingestion must process long-running OCR, multimodal parsing, embedding jobs, or high-volume connector backfills; when work must survive process termination and resume automatically; when multiple workers require stronger coordination; or when the production persistence and indexing topology is selected.
