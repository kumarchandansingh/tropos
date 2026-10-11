# Resolve Runtime Experience

Status: Active product and architecture contract  
Scope: First end-to-end Resolve walking skeleton

## User outcome

A support user can ask a question against governed Tropos knowledge and receive either:

1. a grounded answer whose citations resolve to the exact eligible evidence supplied to generation; or
2. an explicit abstention that explains whether retrieval returned no eligible evidence or the evidence was insufficient.

The first executable surface is the CLI. Its states, objects, and lineage are designed for the eventual **Resolve**, **Evidence**, and **Traces & Incidents** product experience rather than as a throwaway command.

## Reference patterns

| Reference | Pattern adopted | Tropos interpretation |
|---|---|---|
| Glean Assistant | Enterprise answer experience keeps sources visible and permission-aware | Resolve answers remain evidence-first and do not silently fall back to unrestricted world knowledge |
| Phoenix | A request is inspectable as meaningful retrieval/model spans and failures can become eval material | Trace spans use Tropos domain stages such as retrieval, sufficiency, generation, citation validation |
| Langfuse | Prompt/model/runtime provenance is attached to a request | Trace records model deployment, prompt version, latency, token usage, and retrieval strategy without duplicating secrets |
| KCS v6 | Search/reuse while solving, improve/create knowledge from resolution work | Resolve output is a future input to ResolutionEvidence and REUSE/IMPROVE/CREATE, not a generic chatbot transcript |

References:
- https://docs.glean.com/user-guide/assistant/
- https://arize.com/docs/phoenix/learn/tracing
- https://langfuse.com/docs/observability/overview
- https://library.serviceinnovation.org/KCS/KCS_v6/KCS_v6_Practices_Guide/

## Personas and user stories

Primary persona: Support / Resolve User.  
Operational persona: AI Quality / Product Owner.

- As a support user, I want to ask a question against governed enterprise knowledge.
- As a support user, I want the answer to cite the exact evidence used.
- As a support user, I want an explicit abstention rather than plausible unsupported text.
- As a support user, when evidence is insufficient, I want to see the missing or conflicting facts.
- As a quality owner, I want one trace ID that links retrieval, sufficiency, generation, and citation validation.
- As a quality owner, I want traces to contain replay-relevant identities/configuration without copying restricted evidence text by default.
- As a knowledge manager, I want a resolved interaction to be structurally usable later as resolution evidence for REUSE/IMPROVE/CREATE.

## Information architecture

```text
Resolve
├── Ask / Resolve
├── Evidence
└── Resolution history

Traces & Incidents
├── Traces
├── Trace detail
├── Failed / degraded runs
└── Add failure to evaluation dataset

Knowledge Operations
└── future ResolutionEvidence → REUSE / IMPROVE / CREATE
```

This PR implements the runtime contract behind the first two areas and preserves the future KCS hand-off. It does not build a visual frontend.

## UX flow

```text
Question
   ↓
Resolve request created
   ↓
Governed retrieval
   ↓
Retrieval gate
   ├── no eligible evidence
   │      ↓
   │   RETRIEVAL_ABSTAINED
   │
   └── eligible evidence
          ↓
       EvidenceSet
          ↓
       Sufficiency judge
          ├── INSUFFICIENT
          │      ↓
          │   EVIDENCE_INSUFFICIENT
          │   + missing facts / contradictions
          │
          └── SUFFICIENT
                 ↓
              Grounded generation
                 ↓
              Citation resolver
                 ├── all aliases resolve → ANSWERED
                 └── unknown/missing alias → fail closed
```

Every branch emits one trace ID.

## UI state contract

### Answered

```text
Resolve
────────────────────────────────────────
Question
Why did activation fail after certificate rotation?

Answer
The device must be restarted after the certificate rotation ...

Evidence assessment
✓ Sufficient
⚠ Judge status: UNVALIDATED

Evidence
[1] Device runbook
[2] Certificate procedure

[View evidence] [View trace] [Report issue]
```

No user-facing confidence percentage is shown.

### Retrieval abstained

```text
I couldn't find eligible governed evidence for this question.

Evidence examined: 0

[View trace]
```

This is distinct from an LLM/provider failure.

### Evidence insufficient

```text
I don't have enough eligible evidence to answer reliably.

Missing information
• firmware version
• certificate chain

Conflicting support
• ...

Evidence examined: 3

[View evidence] [View trace]
```

### Runtime failure

Provider timeout, malformed structured output, citation-validation failure, and infrastructure failure are operational failures. They must not be rendered as “insufficient evidence.”

## Object-model audit

| Existing / desired concept | Decision |
|---|---|
| `KnowledgeSearchRequest` | Reuse for governed retrieval |
| `RetrievedKnowledgeChunk` | Reuse as eligible ranked retrieval output |
| `EvidenceSet` | Reuse from sufficiency slice as immutable context shared by judge/generator/citations |
| `SufficiencyDecision` | Reuse |
| `LLMInvocationMetadata` | Reuse for judge/generator provenance |
| `RuntimeRequest` | Add as one Resolve request identity/query/access/config boundary |
| `GroundedAnswer` | Add as user-visible answer plus resolved `EvidenceRef` citations |
| `ResolveResult` | Add as typed ANSWERED / RETRIEVAL_ABSTAINED / EVIDENCE_INSUFFICIENT outcome |
| `RuntimeTrace` / spans | Add vendor-neutral trace contract; do not duplicate evidence text |
| Knowledge Article draft | Do not reuse: a Resolve answer and a governed Knowledge Article are different lifecycle objects |
| ResolutionEvidence / KnowledgeDecision | Preserve as later KCS hand-off; do not invent persistence in this PR |

## Functional architecture

```text
tropos ask
   ↓
RuntimeRequest
   ↓
KnowledgeChunkRetriever
   ↓
Retrieval gate
   ↓
EvidenceSet
   ↓
LLMEvidenceSufficiencyJudge
   ↓
┌──────────────────────────────┐
│ insufficient → abstain       │
│ sufficient                   │
└──────────────┬───────────────┘
               ↓
GroundedAnswerGenerator
               ↓
deterministic citation resolution
               ↓
ResolveResult
               ↓
TraceSink
```

## Retrieval abstention boundary

The repository already calibrates strategy-specific top-score thresholds in the evaluation package. Runtime application code must not depend on `tropos.evals`.

For this walking skeleton:

- zero eligible retrieval results always abstain;
- an optional runtime threshold can be supplied explicitly;
- the local CLI does not pretend an arbitrary threshold is calibrated;
- promotion of a calibrated policy from evaluation evidence into versioned runtime configuration remains a separate controlled step.

This preserves the architectural boundary while still making retrieval abstention executable.

## Grounded generation contract

Generation receives only:

```text
query
+ eligible EvidenceSet aliases/text
```

The prompt states that evidence is untrusted data, not instructions.

The structured model response contains:

- answer text;
- evidence aliases such as `E1`, `E2`.

Tropos resolves aliases deterministically to the exact `EvidenceRef` values in the supplied EvidenceSet. Unknown citations fail closed. At least one citation is required for an answered result.

This proves citation identity/integrity. It does not by itself prove claim-level faithfulness; groundedness evaluation remains a separate quality layer.

## Trace contract

One request receives one `trace_id`.

The trace records stage-level metadata for:

- request;
- retrieval strategy and result IDs/scores;
- retrieval-gate decision/config;
- evidence-set ID and evidence IDs;
- sufficiency decision + prompt/model invocation metadata;
- generation prompt/model invocation metadata;
- citation aliases/resolution status;
- final outcome/error type.

By default the trace does **not** duplicate raw chunk/evidence text or API secrets.

Trace answers “what happened?” It is not itself a retry/fallback policy.

## Security

- Retrieval remains the authorization/current-version boundary.
- The CLI is a local-operator trust context, not a production authenticated network boundary; its tenant/groups must not be described as a VerifiedPrincipal.
- Evidence is treated as untrusted data in both sufficiency and generation prompts.
- Generation can only cite evidence supplied to it.
- Provider credentials never enter trace attributes.
- Restricted evidence text is not copied into trace output by default.
- Model-egress policy enforcement for restricted enterprise data remains required before production external-provider use.

## CLI

```text
tropos ask "What should I do after certificate rotation?"
tropos ask "..." --database .tropos/tropos.db --tenant local
tropos ask "..." --tenant acme --group support-l3
```

The first local runtime uses the existing SQLite FTS retriever and the configured Groq deployment. Dense/hybrid runtime composition is not fabricated when an embedding provider/runtime is absent.

## Acceptance evidence

1. a real ingested file can flow from SQLite retrieval into EvidenceSet;
2. zero eligible results return `RETRIEVAL_ABSTAINED` without calling an LLM;
3. insufficient evidence returns `EVIDENCE_INSUFFICIENT` and never calls generation;
4. sufficient evidence invokes grounded generation;
5. every emitted citation resolves to the exact supplied EvidenceSet;
6. unknown citation aliases fail closed;
7. one trace captures stage/config/model/evidence identities without raw evidence text;
8. current sufficiency status remains visibly `UNVALIDATED`;
9. restricted evidence remains excluded before either model call;
10. the runtime path does not import the evaluation package.
