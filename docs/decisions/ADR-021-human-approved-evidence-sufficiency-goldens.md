# ADR-021: Human approval is required for evidence-sufficiency goldens

**Status:** Accepted  
**Date:** 2026-10-11

## Context

Tropos can now measure retrieval relevance, ranking, expected-empty behavior, and a V1 score-based abstention policy.

That does not answer a stronger question:

> Does the retrieved evidence set contain all information required to answer the query completely and safely?

A highly ranked passage can be topically relevant while still missing a critical fact, covering only part of a multi-part question, relying on stale guidance, conflicting with another source, or requiring evidence the current user cannot access.

Google Research formalizes the same distinction as **sufficient context**: a RAG error can arise because the model mishandles adequate context or because the retrieved context itself is insufficient. Its selective-generation work uses context sufficiency to guide abstention rather than treating retrieval relevance as equivalent to answerability.

Tropos also has a practical data-governance problem. The first evidence-set candidates were prepared with AI assistance from a multi-source public survey. Those candidates are useful material for human review, but AI-prepared labels must not silently become golden evaluation truth.

## Decision drivers and constraints

The V1 benchmark must:

- separate retrieval relevance from evidence sufficiency;
- preserve query + evidence-set provenance;
- represent sufficient and insufficient context with explicit reason codes;
- capture the facts a human believes are required to answer;
- preserve missing facts separately from retrieved evidence;
- support conflicting, stale, unauthorized, weak, and non-answer-bearing evidence;
- keep AI-prepared candidate cases distinct from human-approved goldens;
- require explicit human identity before an expected label can become scorable truth;
- fit the existing generic `EvalDataset` / `EvalCase` runtime after approval;
- avoid introducing an LLM sufficiency judge before human labels exist.

## Options considered

### 1. Treat the prepared AI labels as the benchmark

This is fast and would make the dataset executable immediately.

It would make the evaluation circular: AI-generated expectations would be used to judge later AI behavior without an independent human quality boundary.

### 2. Store only a spreadsheet until every case is manually reviewed

This keeps labels human-controlled.

It leaves the repository without an executable schema, validation rules, immutable candidate identities, or a safe path from review to the generic eval runtime.

### 3. Commit unlabelled candidates and make human adjudication the promotion gate

The repository stores query, evidence set, split, pattern/source provenance, and candidate identity. Human reviews are represented explicitly. Only cases marked `approved` with human review plus adjudication can project into a generic `EvalDataset`.

This preserves preparation work while preventing candidate material from becoming a golden by accident.

## Decision

Tropos uses option 3.

The lifecycle is:

```text
public-source survey
        ↓
synthetic query + evidence-set candidate
        ↓
approval = candidate
        ↓
independent human review(s)
        ↓
human adjudication
        ↓
approval = approved
        ↓
generic EvalCase / EvalDataset
        ↓
future sufficiency subject evaluation
```

Candidate cases are valid repository data, but they are **not executable goldens**.

An approved case requires:

- at least one human review;
- an explicit human adjudication;
- a sufficiency label;
- an explicit reason code;
- required facts;
- missing facts when applicable;
- reviewer identity and timestamp;
- an answer/abstain decision.

The label contract is:

| Label | Reason | Missing facts | Answer |
| --- | --- | --- | --- |
| `SUFFICIENT` | `NONE` | empty | allowed |
| `INSUFFICIENT` | non-`NONE` | may be present depending on reason | abstain |

Initial insufficiency reasons are:

- `MISSING_CRITICAL_FACT`
- `PARTIAL_COVERAGE`
- `CONFLICTING_EVIDENCE`
- `STALE_EVIDENCE`
- `UNAUTHORIZED_EVIDENCE`
- `WEAK_SUPPORT`
- `NO_ANSWER_BEARING_PASSAGE`
- `OTHER`

`NONE` is reserved for sufficient evidence.

The generic eval projection uses:

```text
inputs
├── query
├── evidence_set_id
├── evidence[]
├── pattern lineage
└── source provenance

expected
├── label
├── reason
├── required_facts
├── missing_facts
├── should_abstain
├── human_adjudicator
└── human_review_count
```

## Consequences

### Positive

- Human judgment, not an AI-prepared answer key, defines benchmark truth.
- Candidate identities can be versioned and reviewed before labels exist.
- Review disagreements remain visible instead of being overwritten.
- The future model judge can be calibrated against independent human labels.
- The benchmark can represent more failure types than a scalar retrieval threshold.
- Approved cases use the same generic evaluation contracts as other Tropos capabilities.

### Negative / trade-offs

- The 16 initial cases cannot produce a sufficiency score until humans label them.
- Human review adds delivery time and can itself contain disagreement or error.
- Reviewer identity and adjudication become part of benchmark governance.
- The initial public candidates are small and correlated by pattern family.
- A human-approved sufficiency label still does not prove generated-answer quality; generation remains a separate evaluation layer.

## Evidence

Implementation:

- `tropos.evals.evidence_sufficiency`
- `evals/resolve/evidence_sufficiency_candidates_v1.json`
- `scripts/validate_evidence_sufficiency_benchmark.py`
- unit tests enforcing candidate/approved boundaries and label semantics.

Research basis:

- Joren et al., Google Research / ICLR 2025, *Sufficient Context: A New Lens on Retrieval Augmented Generation Systems*: <https://research.google/pubs/sufficient-context-a-new-lens-on-retrieval-augmented-generation-systems/>

## Revisit when

Revisit this decision when:

- enough double-reviewed cases exist to quantify reviewer agreement;
- a model-based sufficiency grader is calibrated against the human set;
- production feedback reveals new insufficiency reason classes;
- reviewer/adjudication workflow needs stronger identity or audit controls;
- the benchmark becomes large enough to require blinded external labels.
