# Tropos Walking Skeleton Design Map

Status: Active cross-PR product/design contract  
Scope: PRs #95–#98 and the visual product surfaces they are preparing  
Purpose: Keep user stories, reference-product patterns, information architecture, UX states, domain objects, and implementation slices aligned.

## Product thesis

Tropos is not a generic chat-with-documents application.

The first product path is:

```text
enterprise source
  → governed ingestion
  → canonical knowledge
  → authorized/current retrieval
  → retrieval abstention
  → evidence sufficiency
  → grounded answer or explicit abstention
  → exact citations + trace
  → later ResolutionEvidence
  → REUSE / IMPROVE / CREATE
```

The executable surface is initially CLI, but the runtime contracts are designed for the future visual product. UI is therefore not treated as a wrapper added after backend design.

## Personas

| Persona | Primary job |
|---|---|
| Support / Resolve User | Resolve a case using trustworthy enterprise evidence |
| Knowledge Manager / SME | Review, improve, approve, and maintain reusable knowledge |
| AI / Platform Admin | Configure sources, models, runtime, and operational health |
| AI Quality / Product Owner | Evaluate quality, compare changes, and control promotion |
| Security / Access Admin | Diagnose identity, permission, and provider-data boundaries |

A single generic “admin” persona must not silently absorb all five responsibilities.

## External reference set

Tropos borrows interaction patterns from mature products but keeps its own domain model.

| Tropos concern | Reference | Pattern to adopt | Do not copy blindly |
|---|---|---|---|
| Sources, connectors, permissions | Glean Admin | Durable source administration and permission-aware access | Glean's complete search/assistant product scope |
| File/source processing | Unstructured Platform | Separate source/configuration from workflow execution/job | Its terminology when Tropos already has stronger canonical knowledge concepts |
| Knowledge ingestion state | Dify Knowledge | Visible processing/index/error states | A RAG-only document model that collapses canonical lifecycle |
| Model/provider setup | Dify model providers | Workspace-level connection management | Provider = model = role conflation |
| Answer UX | Glean Assistant / AI Answers | Permission-aware, source-visible enterprise answers | Silent fallback to unrestricted world knowledge in the first Tropos slice |
| Tracing | Phoenix | Request decomposed into meaningful retriever/LLM stages | Engineering span jargon as the primary end-user UI |
| Prompt/model provenance | Langfuse | Prompt/model/runtime lineage attached to requests | Making observability itself the product |
| Evaluation | Phoenix + Langfuse | Dataset → run → evaluation → experiment; production failures feed datasets | Vanity metric dashboards without decision context |
| Knowledge lifecycle | KCS v6 | Search/reuse while solving; improve/create in workflow; reuse is review | Treating generated articles as final/static content |

Current reference documentation:
- https://docs.glean.com/administration/about
- https://docs.glean.com/user-guide/assistant/how-glean-accesses-info
- https://docs.glean.com/user-guide/assistant/glean-chat/glean-chat-citations/glean-citations
- https://docs.unstructured.io/platform-api/api/overview
- https://docs.dify.ai/
- https://arize.com/docs/phoenix/learn/tracing
- https://langfuse.com/docs/observability/overview
- https://library.serviceinnovation.org/KCS/KCS_v6/KCS_v6_Practices_Guide/030

## Target information architecture

```text
Tropos
│
├── Resolve
│   ├── Ask / Resolve
│   ├── Evidence
│   └── Resolution history
│
├── Knowledge Operations
│   ├── Knowledge queue
│   ├── REUSE / IMPROVE / CREATE
│   ├── Draft articles
│   ├── Review
│   ├── Published knowledge
│   └── Needs update / retired
│
├── Sources & Ingestion
│   ├── Sources
│   ├── Add Source / Upload
│   ├── Ingestion runs
│   ├── Documents / knowledge records
│   └── Failures
│
├── Evaluations
│   ├── Overview
│   ├── Retrieval
│   ├── Evidence sufficiency
│   ├── Generation / groundedness
│   ├── Datasets
│   └── Experiments
│
├── Traces & Incidents
│   ├── Traces
│   ├── Trace detail
│   ├── Failed / degraded runs
│   └── Add failure to evaluation dataset
│
├── Models & APIs
│   ├── Connections
│   ├── Model deployments
│   ├── Role assignments
│   └── Model evaluation evidence
│
├── Prompts & Runtime
│   ├── Prompt versions
│   ├── Runtime configuration
│   └── Policies / fallbacks
│
├── Access & Security
│   ├── Principals / groups
│   ├── Source permission diagnostics
│   ├── Roles
│   └── Data / model-egress policy
│
└── Overview
    ├── Needs attention
    ├── Knowledge health
    ├── Runtime health
    ├── Quality status
    └── Ingestion health
```

Pages are added only when they support a distinct user task. Technical implementation categories such as “vectors” or “embeddings” do not automatically become navigation items.

## Cross-PR design map

| PR | User outcome | Reference patterns | UX / IA contract | Durable objects |
|---|---|---|---|---|
| #95 | Admin can ingest real knowledge and understand what happened | Glean, Unstructured, Dify | Sources, Add Source, Ingestion Runs, document status, failure states | Source connector boundary, RawKnowledgeRecord, canonical KnowledgeDocument/state, KnowledgeChunk, persisted ingestion run/result |
| #96 | Admin can use a real LLM without coupling product logic to one provider | Dify, Langfuse/Phoenix provenance | Models & APIs → Connections → Deployments → Role assignments | ModelProvider, ModelConnection, ModelDeployment, ModelAssignment, LLMInvocationMetadata |
| #97 | Resolve can decide whether eligible evidence is enough and explain why | Phoenix, Langfuse, Glean permission boundary, sufficient-context research | Evaluations → Evidence Sufficiency; Resolve evidence assessment; UNVALIDATED state | EvidenceSet, SufficiencyDecision, LLMInvocationMetadata; human benchmark remains separate |
| #98 | User can ask and get a grounded answer or useful abstention with citations and trace | Glean, Phoenix, Langfuse, KCS | Resolve Ask/Evidence; Traces & Incidents; later Knowledge Operations hand-off | RuntimeRequest, GroundedAnswer, ResolveResult, RuntimeTrace/TraceSpan |

## Sources & Ingestion UX contract

Primary user stories:
- ingest a supported local file;
- distinguish new canonical content from formatting-only change;
- distinguish access/governance change from content version;
- inspect failure/rebaseline state;
- know whether content is available to retrieval;
- later configure enterprise connectors without changing ingestion core.

State language:

| Runtime state | Product language |
|---|---|
| VERSION_CREATED | Available — new version created |
| NO_CHANGE | Available — no content change |
| GOVERNANCE_REFRESHED | Available — access updated |
| REBASELINE_REQUIRED | Action required — rebaseline |
| Failed execution | Failed — inspect stage/error |

Future visual flow:

```text
Sources
  → Add source
  → Configure identity/access
  → Start ingestion
  → Ingestion run
  → canonical knowledge record/version
  → searchable derived projections
```

A source is not an ingestion run. A run is not canonical knowledge. An index is not canonical knowledge.

## Models & APIs UX contract

The product model is:

```text
ModelProvider
  → ModelConnection
  → ModelDeployment
  → ModelAssignment(role)
```

Role examples:
- sufficiency;
- generation;
- eval judge;
- embedding.

Quality attaches to a deployment + prompt/config + benchmark, not to the provider brand.

Credentials:
- are never rendered after entry;
- are referenced, not serialized into domain objects/traces;
- may move from environment-backed bootstrap to an encrypted admin-managed secret store without changing application/domain contracts.

## Evidence Sufficiency UX contract

The decision question is:

> Does the eligible evidence contain enough information to answer the query definitively using only that evidence?

It is not:
- an authorization decision;
- a generic freshness decision;
- a retrieval-score decision;
- a groundedness score for the generated answer.

Before human calibration the visual state is explicit:

```text
Evidence Sufficiency
Status               UNVALIDATED
Human-approved cases 0
No production quality claim can be made yet.
```

No synthetic confidence percentage is shown.

## Resolve UX contract

Answered state:
- answer first;
- exact evidence/citations visible;
- evidence assessment visible;
- trace available for investigation;
- current judge validation status visible to operational users;
- no unrestricted model/world-knowledge fallback in the first slice.

Insufficient state:
- no generated pseudo-answer;
- missing facts and contradictions visible;
- evidence examined is inspectable;
- trace link available.

Retrieval-abstained state:
- distinguished from evidence-insufficient and provider/runtime failure.

Runtime/provider/citation failure:
- treated as operational failure, never relabeled as “insufficient evidence.”

## Traces & Incidents UX contract

Trace answers “what happened?”

Domain stages:
```text
request
→ retrieval
→ retrieval gate
→ evidence set
→ sufficiency
→ generation
→ citation validation
→ outcome
```

The trace should support:
- aggregate list → trace detail;
- failing-stage drill-down;
- later “add failure to evaluation dataset”;
- replay-relevant identities/configuration.

Default trace payload must not duplicate:
- raw restricted evidence text;
- raw API secrets;
- unnecessary personal/source payloads.

Observability is not runtime control. Retry/fallback/policy behavior belongs to versioned runtime policy.

## Knowledge Operations / KCS hand-off

Resolve answers are not Knowledge Articles.

The future lifecycle remains:

```text
Case
  → ResolutionEvidence
  → KnowledgeDecision
      ├── REUSE
      ├── IMPROVE
      └── CREATE
  → KnowledgeArticle
  → Draft
  → Review
  → Published
  → reuse / needs update / revised / retired
```

The Resolve runtime must preserve enough lineage to feed this workflow later without turning chat transcripts into canonical knowledge automatically.

## Object-model guardrail

Before adding a durable object:

```text
existing repository object
  → intended user-facing/product concept
  → same responsibility?
      ├── yes → reuse/extend
      └── no  → prove the new lifecycle/identity responsibility
```

Current runtime spine:

```text
Source
→ RawKnowledgeRecord
→ canonical KnowledgeDocument/state
→ KnowledgeChunk
→ derived indexes

RuntimeRequest
→ retrieval results
→ EvidenceSet
→ SufficiencyDecision
→ GroundedAnswer
→ citations
→ RuntimeTrace
```

Do not create parallel “document”, “evidence”, “job”, “model”, or “trace” abstractions merely for implementation convenience.

## UX design rules

1. Every page answers a user question.
2. Action precedes vanity metrics.
3. Status labels have deterministic semantics.
4. Summary → drill-down → raw operational detail uses progressive disclosure.
5. Empty states are truthful; zero evidence is shown as zero.
6. No invented user-facing confidence.
7. Use domain language before infrastructure jargon.
8. Loading, partial success, failure, permission denial, and recovery are first-class states.
9. Secrets never reappear after entry.
10. Model quality always carries model deployment + prompt/config + benchmark + date/provenance.
11. Every major runtime object has lineage.
12. A number on Overview should lead to the workflow that resolves it.

## Security and trust-boundary rules

- Authorization/current-version filtering happens before evidence reaches LLM stages.
- Retrieved text is untrusted data, not model instructions.
- Caller-supplied CLI groups are a local-operator development context, not a production VerifiedPrincipal.
- Production network entry must later resolve authenticated identity server-side before governed retrieval.
- External-model egress for restricted enterprise evidence requires an explicit data/provider policy boundary.
- Citation resolution may only resolve evidence supplied to generation.

## Evaluation and promotion rules

```text
production trace/failure
  → curated EvalCase
  → versioned EvalDataset
  → baseline/candidate EvalRun
  → case-level comparison
  → gate/promotion decision
```

Human-reviewed labels remain authoritative for sufficiency calibration. Model outputs never promote themselves into goldens.

## Definition of Done for product-affecting PRs

A product-affecting PR is not complete solely because CI passes.

It must address, when relevant:
- persona and user outcome;
- user stories/use cases;
- mature-product/reference pattern and what is deliberately not copied;
- information-architecture impact;
- happy path and failure/empty/permission states;
- object/data-model audit;
- functional architecture;
- security boundary;
- observability/replay impact;
- tests/evals;
- public docs;
- CI/regression gates;
- unsupported claims explicitly avoided.

This map is the default review checklist for the next visual UI/API/connector slices.
