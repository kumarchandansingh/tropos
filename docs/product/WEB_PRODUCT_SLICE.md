# First Web Product Slice — Sources & Ingestion + Resolve

Status: Implemented in this PR  
Scope: Local product UI over the proven Resolve walking skeleton

## User / business outcome

Tropos is no longer CLI-only for the first operational workflow.

An AI / Platform Admin can upload a supported knowledge file and understand the ingestion outcome. A Support / Resolve User can ask a question against governed knowledge, receive either a grounded cited answer or an explicit abstention, inspect the evidence admitted to generation, and open the trace for the request.

This slice wraps the already-proven runtime rather than inventing a parallel demo path.

## Reference products reviewed

| Reference | Pattern used by Tropos |
|---|---|
| Glean Admin | Sources are managed objects and source administration is permission-aware rather than a generic file picker |
| Glean Assistant | Answers are source-aware and citations are visible to the user |
| Langfuse | One request maps to one trace composed of meaningful functional steps |
| Dify / enterprise knowledge tools | Knowledge ingestion is presented with explicit processing / availability state rather than “upload succeeded” only |

References:

- https://docs.glean.com/administration/about
- https://docs.glean.com/user-guide/assistant/how-glean-accesses-info
- https://langfuse.com/docs/observability/overview
- https://docs.dify.ai/

## Personas and user stories

AI / Platform Admin:
- add governed knowledge;
- distinguish new version, no canonical content change, governance-only change, action-required, and failure states.

Support / Resolve User:
- ask against governed knowledge;
- get a grounded answer only when eligible evidence is sufficient;
- inspect the exact evidence and citation lineage.

AI Quality / Product Owner:
- inspect runtime decision, validation status and trace;
- never see an invented confidence score when quality is still unvalidated.

## Information architecture

    Tropos
    ├── Sources & Ingestion
    │   ├── Upload
    │   └── Latest ingestion result
    ├── Resolve
    │   ├── Ask
    │   ├── Answer / abstention
    │   ├── Evidence
    │   └── Decision
    └── Observability
        ├── Runtime summary
        ├── Recent traces
        └── Trace detail

This is intentionally not a vanity dashboard.

## Object / domain model audit

| UI concept | Existing runtime concept | Decision |
|---|---|---|
| Upload | LocalFileSourceConnector + canonical ingestion pipeline | Reuse |
| Ingestion result | IngestionResult / persisted run outcome | Reuse |
| Question | RuntimeRequest | Reuse |
| Evidence panel | EvidenceSet / EvidenceItem | Reuse |
| Sufficiency badge | SufficiencyDecision | Reuse |
| Answer | GroundedAnswer | Reuse |
| Citation | EvidenceRef | Reuse |
| Trace | RuntimeTrace / TraceSpan | Reuse |
| Browser session | presentation concern only | Do not create domain object |

No parallel knowledge, evidence, answer or trace entity is introduced.

## UX flow and states

### Sources & Ingestion

    Choose / drop file
    → validate filename / type / size
    → upload
    → parse / normalize / version / chunk / persist / FTS
    → show exact runtime outcome

States: empty, selected, loading, available/new version, available/no change, available/access updated, action-required/rebaseline, unsupported/empty/oversized/runtime failure.

A formatting-only NO_CHANGE result must not appear as a new knowledge version.

### Resolve

    Enter question
    → governed BM25 retrieval
    → retrieval gate
    → EvidenceSet
    → evidence sufficiency
    → insufficient: abstain
    → sufficient: grounded generation
    → deterministic citation resolution
    → answer + evidence + trace

States: empty, loading, answered, retrieval-abstained, evidence-insufficient, runtime/provider failure, trace unavailable.

UNVALIDATED remains visible. The UI does not convert it into a confidence percentage.

## UI design contract

Sources & Ingestion primary action: Upload & ingest.

Latest result shows product-language status, runtime outcome, reason, chunks written, knowledge ID and run ID.

Resolve primary action: Resolve.

The answer is the primary reading surface. Supporting evidence and runtime decision are separate panels. Evidence shows alias, source title, rank, score and exact locator. Decision shows sufficiency label, validation status, failure type and trace drill-down.

Trace expands functional stages rather than dumping hidden prompts or raw restricted evidence.

## Functional architecture

    Browser
      ├── POST /api/ingest
      │     → existing ingestion services
      │     → SQLite canonical state / FTS projection
      │
      └── POST /api/resolve
            → SQLiteFtsKnowledgeRetriever
            → retrieval gate
            → EvidenceSet
            → Groq sufficiency judge
            → grounded generator
            → citation resolver
            → JsonlTraceSink

    Browser
      └── GET /api/traces/{trace_id}
            → local trace detail

The presentation layer composes existing application and domain contracts. It does not bypass retrieval eligibility or citation validation.

## Technical architecture

The first UI is a single local same-origin HTTP application.

- Python's standard-library HTTP server provides HTML and JSON endpoints.
- No additional web framework dependency is introduced in this slice.
- Existing SQLite remains the system of record for this slice.
- Uploaded bytes are staged in a temporary directory and run through the canonical local-file connector.
- Temporary staged files are deleted after ingestion.
- Trace detail and the Observability workspace read the existing JSONL trace sink through a query projection.
- tropos web starts on 127.0.0.1:8000 by default.

A separate React / Next.js deployment is deferred until the interaction model and API contracts have been exercised. The product object model must survive that later presentation change.

## Security

- Default binding is localhost only.
- The browser never receives the Groq API key.
- Upload filenames are reduced to a safe basename and unsupported suffixes are rejected.
- Upload size is capped at 10 MB in this slice.
- Access policy continues to be attached during ingestion.
- Resolve still filters by tenant/groups before evidence reaches the LLM.
- Trace output still avoids raw query/evidence duplication by default.
- This local slice does not establish production authentication or VerifiedPrincipal; that remains required before remote/multi-user deployment.

## Observability

The answer includes trace_id. The trace panel exposes request, retrieval, retrieval gate, evidence set, sufficiency, generation and citation-validation stages. No new trace model is invented.

## Acceptance evidence

1. tropos web serves the browser UI locally.
2. supported uploads reach the canonical ingestion pipeline.
3. successful upload is immediately searchable through existing FTS.
4. unsafe or unsupported filenames are rejected.
5. Resolve preserves existing answer / abstention semantics.
6. evidence and UNVALIDATED sufficiency status are visible.
7. trace detail is retrievable by exact trace ID.
8. credentials are never returned to the browser.
9. Python tests, strict mypy, Ruff and existing evaluation/regression gates remain green.

## Deferred decisions

Production authentication, remote deployment, connector catalog, durable SourceConnection, ingestion-run history, trace search, RBAC web administration, Models & APIs UI, dense/hybrid runtime promotion, production database/queue/object storage, and a separate frontend framework remain deferred rather than simulated.


## Operations UX V2

The initial slice was strengthened after live use exposed three operational gaps: duplicate/no-change uploads were too easy to misread, errors were only transient banners, and trace inspection was buried inside a single Resolve result. The follow-on design and implementation are documented in `docs/product/OPERATIONS_UX_V2.md`.
