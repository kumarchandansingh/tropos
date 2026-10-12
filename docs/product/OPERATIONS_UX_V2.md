# Operations UX V2 — Ingestion Feedback, Error Recovery, Observability

Status: Design for implementation  
Scope: Strengthen the existing local web product slice without changing the core Resolve domain model.

## 1. User / business problem

The first web slice proved the runtime, but the current UI is too thin for real operational use.

Three failures are visible:

1. **Weak ingestion feedback.** Re-uploading the same document can legitimately result in `NO_CHANGE`, but the current UI only has a single latest-result card and does not make duplicate/no-change handling prominent enough. Users can interpret a correct no-op as “nothing happened.”
2. **Errors are not operationally useful.** Failures are shown only as a generic top banner. The failing action, stage, HTTP/runtime category, recovery action and retained state are not visible.
3. **Observability is buried inside one Resolve result.** Earlier Tropos design already defined a dedicated trace/incident workspace. The first slice only added “Open trace” inside Resolve, so there is no way to review recent runs, find failures, compare outcomes or inspect runtime signals across requests.

The outcome of this build is a stronger operator experience rather than additional AI complexity.

## 2. Personas

### Support / Resolve User

Needs to know whether Tropos answered, abstained or failed; why; what evidence was used; and what to do next.

### AI / Platform Admin

Needs to see ingestion outcomes including duplicate/no-change, processing failures and source status without guessing from a blank screen.

### AI Quality / Product Owner

Needs a trace list and trace detail view to inspect retrieval, gating, sufficiency, generation, tokens, latency and runtime/config lineage.

### Security / Access Admin

Needs observability that does not silently expose raw restricted evidence, prompts, secrets or credentials.

## 3. Analogous products reviewed

Tropos should copy durable interaction patterns, not visual styling.

### Langfuse

Useful patterns:
- one trace represents the complete request lifecycle;
- traces decompose into typed observations/spans;
- generation observations carry model, token and latency data;
- production traces can feed later evaluation workflows.

Tropos adapts this into domain stages: request, retrieval, retrieval gate, EvidenceSet, sufficiency, generation and citation validation.

### Arize Phoenix

Useful patterns:
- investigate production failures from trace/session data;
- connect traces to evaluation workflows;
- separate operational inspection from benchmark/evaluation views.

Tropos keeps “Observability” separate from “Evaluations,” with future failure → eval-case promotion explicitly deferred until the command exists.

### Glean Admin / connector monitoring

Useful patterns:
- sync/indexing outcome is a durable operational state, not a transient toast;
- health and troubleshooting are first-class;
- permission-aware indexing is visible to administrators.

Tropos applies this to file ingestion outcomes and source readiness.

### Existing Tropos design

Prior design already specified:
- trace list: status, retrieval, sufficiency, answer/abstention, latency;
- trace detail: identity, candidates/scores, eligibility gates, EvidenceSet, sufficiency/missing facts, generation, citations, tokens/cost/latency, runtime/config lineage;
- progressive disclosure;
- actionable failures;
- duplicate/no-content-change must explicitly explain that the existing version was retained.

## 4. Information architecture

This build changes navigation to:

    Tropos
    ├── Sources & Ingestion
    │   ├── Upload
    │   ├── Result / no-change / error feedback
    │   └── Session activity
    ├── Resolve
    │   ├── Ask
    │   ├── Answer / abstention / error
    │   ├── Evidence
    │   └── Decision summary
    └── Observability
        ├── Runtime health summary
        ├── Recent traces
        ├── Filters
        └── Trace detail

The future target name “Traces & Incidents” remains valid for the full product. This local slice uses “Observability” because it contains runtime summary plus traces and does not yet have an incident object/workflow.

## 5. UX flows and states

### 5.1 Sources & Ingestion

Happy path:

    choose file
    → upload
    → processing
    → VERSION_CREATED
    → available / indexed

No-change path:

    choose previously-ingested identical file
    → upload
    → canonical comparison
    → NO_CHANGE
    → explicit information state:
       “No content change. Existing knowledge version retained.”
    → show knowledge ID + run ID + chunks written = 0

Governance-only path:

    same content, changed access policy
    → GOVERNANCE_REFRESHED
    → explicit “Content unchanged; access metadata refreshed.”

Failure path:

    upload
    → validation/parser/persistence failure
    → inline operation error card
    → show:
       - human title,
       - error category/code,
       - exact server message,
       - whether prior knowledge remains unchanged,
       - retry affordance.

Empty/loading/partial states remain explicit.

### 5.2 Resolve

Happy:

    ask
    → resolving
    → ANSWERED
    → answer + citations + evidence + decision + trace link

Abstention:

    ask
    → retrieved evidence
    → INSUFFICIENT
    → human-readable explanation
    → missing facts shown as a list
    → no invented answer

Retrieval abstention:

    ask
    → no eligible evidence / gate fail
    → explanation that no evidence passed the retrieval gate

Runtime failure:

    ask
    → provider/schema/timeout/runtime failure
    → inline Resolve error panel
    → display:
       - “Resolve failed”
       - server error code/category
       - message
       - retry action
       - no fake answer state

### 5.3 Observability

Landing page:

    runtime health cards
    + recent trace table
    + outcome filter
    + failure-first view

Trace list columns:
- outcome/status;
- trace ID;
- request ID;
- retrieval strategy;
- result count;
- gate result;
- sufficiency;
- model;
- model latency;
- input/output tokens;
- recorded time.

Trace detail uses progressive disclosure:

1. Identity
   - trace ID, request ID, outcome, recorded time
   - runtime config fingerprint
2. Retrieval
   - strategy version
   - candidate chunk IDs
   - ranks/scores
3. Eligibility gate
   - threshold, top score, pass/abstain reason
4. Evidence
   - evidence set ID and aliases/chunk IDs
5. Sufficiency
   - label, failure type, validation status
   - model/deployment/prompt version
   - latency/tokens
6. Generation
   - model/deployment/prompt version
   - latency/tokens
7. Citation validation
   - aliases and resolved chunk IDs
8. Missing instrumentation
   - cost: “Not captured” until model-pricing contract exists
   - raw prompts/evidence: intentionally not recorded in local trace

The trace page must never imply data exists when it is not captured.

## 6. UI design contract

### Visual direction

The first UI is too small and sparse at desktop width. V2 should:
- increase usable content width;
- use a denser enterprise operations layout;
- strengthen typography hierarchy;
- make status colors secondary to text labels;
- reduce excessive empty whitespace;
- use tables for operational collections and cards for decisions/details;
- keep the dark left navigation but strengthen active state and icon-less affordances;
- preserve restrained, professional styling.

### Error component

Every failed action uses one shared visual contract:

    [Failure title] [ERROR badge]
    Human message
    Technical detail (expandable / smaller)
    Stage / error code
    Retry action where safe

Top-level transient banners remain only for unexpected shell/network failures.

### Status language

Use:
- Available
- No content change
- Access updated
- Action required
- Answered
- Evidence insufficient
- Retrieval abstained
- Runtime failed
- Unvalidated

Do not expose raw enum names as the primary user-facing label.

## 7. Domain / data model audit

| UI need | Existing concept | Decision |
|---|---|---|
| New ingestion | IngestionResult | Reuse |
| Duplicate/no change | IngestionOutcome.NO_CHANGE | Reuse; improve presentation |
| Governance-only change | GOVERNANCE_REFRESHED | Reuse |
| Ingestion error | HTTP/runtime exception | Add presentation error envelope only |
| Resolve error | runtime exception | Add presentation error envelope only |
| Trace list | JsonlTraceSink snapshots | Add read/query projection, no new trace domain entity |
| Trace detail | RuntimeTrace / TraceSpan snapshot | Reuse |
| Trace recorded time | not currently stored | Extend JSONL snapshot persistence metadata |
| Runtime metrics | derived from trace snapshots | Add projection only |
| Incident | not implemented | Do not invent |
| Eval-case promotion | generic eval framework exists, trace promotion command absent | Do not fake action |
| Cost | not captured | Show “Not captured”; do not calculate invented cost |

## 8. Functional architecture

### Error envelope

HTTP errors become:

    {
      "error": {
        "code": "UNSUPPORTED_FILE" | "INGESTION_FAILED" | "MODEL_RUNTIME_FAILED" | ...,
        "stage": "upload" | "ingestion" | "resolve" | "trace",
        "message": "...",
        "retryable": true|false
      }
    }

The old `detail` string can remain for compatibility during this local slice, but the UI consumes the structured envelope.

### Trace persistence and projection

RuntimeTrace
→ JsonlTraceSink
→ snapshot + recorded_at
→ trace reader
→ recent trace summaries / aggregate metrics
→ Observability UI.

No raw query/evidence content is added to the trace store.

### Observability metrics

Derived locally from stored traces:
- trace count;
- answered count;
- abstention count;
- runtime failure count;
- answer rate;
- total model calls;
- input/output token totals;
- average captured model latency.

No external telemetry backend is introduced in this build.

## 9. Technical architecture

Keep the current dependency-free local HTTP server for this iteration.

Add:
- `GET /api/observability` for summary + recent trace projections;
- `GET /api/traces/{trace_id}` remains exact trace detail;
- structured error envelope helper;
- recorded timestamp in JSONL trace snapshots;
- stronger single-page UI with an Observability workspace.

Do not introduce:
- authentication;
- remote bind by default;
- background jobs;
- new frontend framework;
- OpenTelemetry exporter;
- Langfuse/Phoenix dependency.

Those can come after the local product workflow is coherent.

## 10. Security / privacy

- Default server remains localhost-only.
- No API key or Authorization header is returned to the browser.
- Raw query/evidence text remains excluded from trace snapshots.
- Trace list shows fingerprints/IDs and operational metadata only.
- Upload validation and 10 MB cap stay in force.
- Structured error messages must not include API keys.
- Provider error sanitization remains owned by the Groq adapter.
- Remote/multi-user deployment still requires VerifiedPrincipal and access-controlled observability.

## 11. Observability of observability

The page must distinguish:
- captured;
- unavailable/not captured;
- unvalidated.

It must not infer cost, confidence or quality scores that are absent.

## 12. Acceptance evidence

The PR is acceptable when:

1. re-uploading identical content returns and visibly renders “No content change. Existing knowledge version retained”;
2. upload errors render inline with code/stage/message/retryability;
3. Resolve runtime errors render inline instead of only as a transient banner;
4. insufficient evidence renders rationale and missing facts;
5. Observability appears in navigation;
6. Observability lists recent traces and filters by outcome;
7. trace detail exposes retrieval, gate, evidence, sufficiency, generation and citation stages;
8. summary shows trace outcomes, token totals and captured model latency;
9. trace snapshots get a recorded timestamp without raw query/evidence payloads;
10. CI, Ruff, strict mypy, tests, docs governance and existing quality gates pass.

## 13. Deferred

- real incident lifecycle;
- trace → eval-dataset promotion action;
- cost pricing/model table;
- distributed tracing / OpenTelemetry export;
- environment filters;
- retention controls;
- saved views;
- user/session identifiers;
- production authentication / authorization;
- ingestion history persisted as a dedicated query model;
- remote deployment.

These remain explicit backlog items rather than fake controls in the UI.
