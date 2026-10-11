# Evidence Sufficiency Experience

Status: Active product and architecture contract  
Scope: Resolve runtime sufficiency decision  
Implementation note: runtime decisions are operational only until human calibration.

## User outcome

A Resolve user receives an answer only when the **eligible evidence** contains enough information to support a definitive response. When it does not, Tropos exposes the missing or conflicting information instead of presenting a weak answer as fact.

An AI Quality / Product Owner can inspect the same decision and see that the current model judge is **UNVALIDATED** until it is calibrated against human-approved cases.

## Reference patterns

| Reference | Pattern adopted | Tropos interpretation |
|---|---|---|
| Phoenix | Inspect model/retrieval decisions at case level and turn failures into evaluation material | Sufficiency decisions retain evidence-set and model invocation lineage |
| Langfuse | Link model output to prompt/model/runtime provenance | Every decision records prompt/deployment invocation metadata |
| Glean | Permission-respecting enterprise evidence is selected before answer generation | Authorization belongs to governed retrieval, not the LLM judge |
| Google sufficient-context research | Separate retrieval relevance from whether context is actually enough | Sufficiency is its own decision layer after retrieval/abstention |

References:
- https://arize.com/docs/phoenix/
- https://langfuse.com/docs
- https://docs.glean.com/
- https://research.google/pubs/sufficient-context-a-new-lens-on-retrieval-augmented-generation-systems/

## Personas and user stories

Primary user persona: Support / Resolve User.  
Operational persona: AI Quality / Product Owner.

- As a support user, I want Tropos to answer only when its eligible enterprise evidence is sufficient.
- As a support user, when Tropos cannot answer, I want to know what information is missing.
- As a quality owner, I want to inspect the immutable evidence set that was judged.
- As a quality owner, I want model-judge output clearly marked unvalidated until human calibration exists.
- As a security owner, I want authorization/current-version/integrity controls to execute before any evidence reaches the judge.

## Information architecture

```text
Evaluations
└── Evidence Sufficiency
    ├── Status
    ├── Benchmark
    ├── Decisions
    └── Case detail

Resolve
└── Evidence assessment
    ├── Sufficient
    └── Insufficient → missing facts / contradictions
```

## UX flow

```text
User question
   ↓
Governed retrieval
   ↓
Deterministic eligibility controls
   ├── authorized
   ├── current canonical version
   └── evidence integrity
   ↓
Retrieval abstention
   ↓
Immutable eligible EvidenceSet
   ↓
LLM sufficiency judge
   ├── SUFFICIENT
   │      ↓
   │   eligible for grounded generation
   │
   └── INSUFFICIENT
          ↓
       abstain
       + missing facts / contradictions
```

The judge is not asked whether the user is authorized, whether a document is globally fresh, or whether retrieval scores are high enough. Those are different system responsibilities.

## UI state contract

Before human calibration:

```text
Evidence Sufficiency
────────────────────────────
Status               ⚠ UNVALIDATED
Human-approved cases 0
Model                 current assigned deployment
Prompt                resolve-evidence-sufficiency-v1

No production quality claim can be made yet.
```

Sufficient runtime state:

```text
Evidence assessment
✓ Sufficient

Required facts     ...
Supported facts    ...
Evidence examined  ...
```

Insufficient runtime state:

```text
I don't have enough eligible evidence to answer reliably.

Missing information
• ...

Conflicting support
• ...

[View evidence]
```

No confidence percentage is displayed because no calibrated user-facing interpretation exists.

## Object-model audit

| Existing / desired concept | Decision |
|---|---|
| `RetrievedKnowledgeChunk` | Reuse as authorized/current ranked retrieval output |
| `EvidenceRef` | Reuse as durable reference to exact chunk |
| `EvidenceSet` | Add as first-class immutable eligible context for judge/generation/trace/eval |
| `SufficiencyDecision` | Add as Resolve runtime decision |
| Human benchmark `EvidenceSufficiencyCase` | Keep separate; it is evaluation specification, not runtime state |
| `LLMInvocationMetadata` | Reuse for provider/model/prompt/latency/token lineage |

## Sufficiency semantics

The exact question is:

> Does the eligible evidence contain enough information to answer the query definitively using only that evidence?

Runtime failure types:

- `MISSING_CRITICAL_FACT`
- `PARTIAL_COVERAGE`
- `CONFLICTING_SUPPORT`
- `NO_ANSWER_SUPPORT`
- `OTHER`

`NONE` is valid only for a sufficient decision.

`UNAUTHORIZED_EVIDENCE`, generic `STALE_EVIDENCE`, and `WEAK_SUPPORT` are not model-judge categories. Unauthorized/current-version eligibility is deterministic upstream behavior; vague weak-support semantics are not introduced until human evidence demonstrates a distinct need.

## Functional architecture

```text
KnowledgeChunkRetriever
   ↓
authorized/current RetrievedKnowledgeChunk[]
   ↓
retrieval abstention
   ↓
EvidenceSet
   ↓
LLMPort.complete_structured
   ↓
SufficiencyDecision
   + LLMInvocationMetadata
```

The evidence prompt explicitly tells the model that retrieved content is untrusted data and must not be followed as instructions.

## Validation boundary

The current judge is operationally executable but `UNVALIDATED`.

Human candidate review remains authoritative:

```text
candidate cases
  → independent human review
  → adjudication
  → approved goldens
  → judge calibration
```

Model output never promotes or edits benchmark labels.

The dangerous quality direction to measure after human labels exist is **false sufficient**: Tropos says context is sufficient when a human says it is not.

## Acceptance evidence

1. eligible retrieval output can be frozen into a unique EvidenceSet with stable EvidenceRefs;
2. the real judge uses the typed LLM port and structured schema;
3. sufficiency decisions reject internally inconsistent “sufficient + missing facts” outputs;
4. every current model decision is marked `UNVALIDATED`;
5. authorization/staleness are removed from judge reason taxonomy;
6. prompt treats evidence as untrusted data;
7. benchmark candidates remain human-gated and model predictions cannot become ground truth.
