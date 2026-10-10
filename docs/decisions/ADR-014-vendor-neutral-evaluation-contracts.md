# ADR-014: vendor-neutral evaluation contracts

**Status:** Accepted  
**Date:** 2026-10-10

## Context

Tropos already has a strong retrieval-specific evaluation catalogue, runner and SQLite store, while Training has a separate deterministic generation evaluator. Resolve now introduces Knowledge Article, classification and Next Best Action evaluation needs. A hosted evaluation platform such as LangSmith may improve execution and visualization, but making a vendor schema the canonical product-quality model would couple Tropos correctness semantics to one tool.

## Options considered

1. Make LangSmith datasets/runs the canonical evaluation model.
2. Build independent evaluation structures separately inside each capability.
3. Define reusable Tropos-owned contracts and add vendor adapters later.

## Decision

Adopt reusable vendor-neutral contracts for dataset, case, run, observation, score, subject/configuration and evaluator identity.

Cases explicitly record scope, approval state and origin. Datasets are versioned and fingerprinted. Scores record whether they came from deterministic logic, a model judge or a human. Run provenance remains separate from factual content evidence.

Existing retrieval evaluation infrastructure is not replaced in this slice. It remains the executable baseline and will be reconciled incrementally with the generic contracts.

## Consequences

### Positive

- Resolve, Training and future capabilities can share quality concepts without sharing capability-specific metrics.
- Approved golden cases remain under Tropos/version-control ownership.
- LangSmith, Langfuse, Phoenix or another platform can be replaced behind adapters.
- Run reproducibility and score provenance are explicit.
- Component and end-to-end evaluation use one vocabulary.

### Negative / trade-offs

- Some concepts temporarily exist both in the older retrieval-specific implementation and the new generic contracts.
- Adapter and migration work is required before hosted tooling can consume the contracts.
- Generic contracts cannot encode every capability-specific expectation; specialized evaluators remain necessary.

## Evidence

- `apps/api/src/tropos/evals/contracts.py`
- `apps/api/tests/unit/evals/test_contracts.py`
- `docs/architecture/EVALUATION_CONTRACTS.md`

## Revisit when

Revisit the boundary if multiple hosted providers require materially incompatible concepts, if generic contracts become too weak for capability-specific evaluation, or if regulatory/audit requirements require stronger immutable identity and approval semantics.
