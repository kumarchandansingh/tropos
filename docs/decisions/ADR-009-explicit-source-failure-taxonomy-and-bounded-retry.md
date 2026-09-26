# ADR-009: Explicit source failure taxonomy and bounded retry

**Status:** Accepted  
**Date:** 2026-09-26

## Context

Tropos now has a replaceable source connector boundary. External source systems will eventually introduce transient network failures, throttling, authentication problems, configuration errors, and permanent record-level failures.

If every connector or orchestration layer catches generic exceptions and retries independently, the same failure can be retried multiple times at multiple layers, terminal failures can loop indefinitely, and recovery ownership becomes unclear.

The current connector contract captures one record at a time and does not yet require a distributed workflow engine or durable multi-record sync coordinator.

## Options considered

1. Let each connector implement ad hoc retry loops around vendor SDK calls.
2. Catch all exceptions in `IngestFromSource` or `IngestKnowledge` and retry generically.
3. Define an explicit source failure taxonomy and compose bounded retry around connectors through a reusable decorator.

## Decision

Tropos will classify source-capture failures as retryable or terminal at the source boundary.

`RetryableSourceError` is the base for failures that may succeed without changing the requested record. `SourceUnavailableError` represents temporary source/network unavailability. `SourceRateLimitedError` represents source throttling and may carry a retry-after hint.

Authentication, configuration, missing-record, unsupported-artifact, and source-identity failures are terminal at the generic retry boundary. A vendor adapter may perform source-specific recovery such as refreshing an expired token before surfacing `SourceAuthenticationError`.

`RetryingSourceConnector` wraps any `KnowledgeSourceConnector` and retries only explicitly retryable failures. `SourceRetryPolicy` provides bounded exponential backoff. Source-provided retry-after guidance takes precedence over computed backoff.

The generic retry layer does not catch arbitrary `Exception`, parse source content, refresh vendor credentials, persist sync checkpoints, or coordinate bulk synchronization.

## Consequences

### Positive

- retry ownership is explicit and reusable across future connectors;
- permanent failures are not retried indefinitely;
- transient failures receive bounded retry with predictable backoff;
- rate-limit guidance can be honored without vendor logic entering core ingestion;
- `IngestFromSource` and `IngestKnowledge` remain free of source-specific retry branches;
- reliability behavior can be tested deterministically through an injected sleeper.

### Negative / trade-offs

- source adapters must map vendor-specific exceptions into the Tropos failure taxonomy;
- authentication refresh remains adapter-specific rather than solved by the generic wrapper;
- no jitter is applied yet because Tropos does not run highly concurrent distributed connector workers;
- retries are in-process and do not survive process termination;
- durable sync checkpoints, partial-batch recovery, monitoring, and replay remain future work.

## Evidence

- `apps/api/src/tropos/core/application/ports/sources.py`
- `apps/api/src/tropos/core/application/sources/reliability.py`
- `apps/api/tests/unit/core/application/sources/test_reliability.py`
- `docs/architecture/CONNECTOR_RELIABILITY.md`

## Revisit when

Revisit this decision when connectors perform long-running or high-volume synchronization, when retry attempts must survive process termination, when a distributed queue/worker topology is introduced, or when production source APIs require more advanced rate-control and circuit-breaking behavior.
