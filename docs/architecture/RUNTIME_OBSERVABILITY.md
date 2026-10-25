# Runtime observability: OpenTelemetry bridge (OBS-101A)

## Scope and intent

Tropos retains the application-owned `RuntimeTrace` and its stages as the canonical
record of Resolve decisions. `JsonlTraceSink` remains the default local sink.
`CompositeTraceSink` can route the same record to multiple consumers, including
`OpenTelemetryTraceSink` in the infrastructure adapters layer.

```text
ResolveQuestion -> RuntimeTrace -> TraceSink
                                     |-- JsonlTraceSink
                                     \-- OpenTelemetryTraceSink -> OTel SDK/backend
```

The OpenTelemetry adapter does not need to be imported into domain or Resolve
application code. Composition roots choose the sinks. OBS-101A introduces the
adapter and its mapping tests but **does not enable OTel export by default**.
The local web UI and CLI continue to use JSONL.

## Retrospective-span limitation

OBS-101A maps a completed `RuntimeTrace` into a root
`tropos.resolve` span and children corresponding to recorded Resolve stages.
The root carries `tropos.mapping_mode=retrospective`, the original
`tropos.trace_id`, and `tropos.outcome`.

An OTel span emitted this way measures export time, **not** the original
retrieval/generation duration. The existing `latency_ms` attributes preserve
the runtime's measured per-stage elapsed time. Original OTel timing, nesting
during execution, and context propagation are deferred to OBS-101B.

## Data governance

The adapter uses an explicit operational-attribute allowlist. Unknown
attributes are omitted rather than automatically forwarded. Exported
attributes can include retrieval strategy, result count, model identifier,
prompt version, token counts, failure classifications and measured latency.

Raw query, evidence body, generated answer, tenant identifiers, request IDs,
evidence-set IDs and chunk IDs are **not** exported by this adapter.
OTel `tropos.trace_id` is a generated correlation identifier, not a tenant
or user-provided value. New attributes require explicit review before
expanding the allowlist.

## Acceptance criteria

1. Parent and child span names preserve Tropos runtime stage semantics.
2. Operational attributes preserve their typed values.
3. Error status is mapped to OTel ERROR, without emitting raw exception messages.
4. Governed identifiers and content are excluded by default.
5. JSONL behavior remains unchanged.
6. Application/domain code has no OTel SDK dependency.
7. Tests run using an in-memory OTel exporter, without an external service.

## Follow-up work

OBS-101B will instrument operations while they execute and capture real span
timing and parent/child context. Collector, OTLP backend configuration,
production sampling/retention, dashboards and LangSmith integrations are out
of scope for OBS-101A.


## OBS-101B: live request instrumentation

The `LiveSpanRecorder` application port exposes a context manager for measured
execution operations. Resolve creates `resolve.request` as the parent operation
and live child spans for `resolve.retrieval`, `resolve.sufficiency`, and
`resolve.generation` when those operations run. In an early-abstention path
there are no sufficiency or generation spans. The previous `RuntimeTrace`
and local JSONL sink remain unchanged.

The `OpenTelemetryLiveSpanRecorder` infrastructure adapter creates nested
OTel spans using `start_as_current_span`; span duration represents actual
wall-clock execution. Its attribute policy deliberately exports only
`tropos.mapping_mode=live` and the exception type for error cases. It does
not record exception messages, queries, evidence, answers, or customer IDs.

For a local opt-in console demonstration, set `TROPOS_OTEL_CONSOLE=1` before
starting `tropos web` or `tropos ask`. The default is off, with no external
export configured. OBS-101A's retrospective sink is still available as a
separate adapter but is not enabled alongside live instrumentation, to avoid
duplicating the same Resolve request as two trace trees.

Future work includes instrumenting evidence/citation sub-stages and attaching
governed safe attributes to live spans, followed by an OTLP exporter/backend.
