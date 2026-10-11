# ADR-019: Converge retrieval evaluation on the generic EvalRun runtime

**Status:** Accepted  
**Date:** 2026-10-11

## Context

Tropos developed retrieval evaluation through two working execution paths.

The saved catalogue path executes isolated retrieval scenarios, records detailed hits and invariants in a retrieval-specific store, and bridges the saved report into the generic experiment model for baseline-versus-candidate comparison.

The real-model path separately evaluates BM25, dense retrieval, and hybrid Reciprocal Rank Fusion (RRF) through `evaluate_retrieval`, builds a custom aggregate report, and applies a separate authorization gate.

Both paths measure the same product boundary: whether a retrieval subject returns the expected current and authorized evidence. Maintaining separate execution and scoring logic creates several risks:

- invariant semantics can diverge across retrieval strategies;
- a new metric or case contract must be implemented twice;
- real-model results do not naturally use the same run persistence and comparison model as pull-request regression evidence;
- benchmark expansion increases the amount of duplicated evaluation machinery.

PR #87 also introduced a complete enterprise-support benchmark that can project the same support scenarios into retrieval, Resolve decision, and Knowledge Article evaluation contracts. That dataset needs a stable execution model before it is expanded toward release-scale evidence.

## Decision drivers and constraints

The retrieval evaluation runtime must:

- run BM25, dense, and hybrid retrievers through identical case and invariant semantics;
- keep authorization, currentness, evidence integrity, and result-contract checks separate from tunable retrieval quality;
- preserve case-level evidence rather than only aggregate scores;
- compare subjects on the same immutable dataset snapshot;
- preserve code, dependency, model, and strategy provenance;
- allow deterministic PR regression gating and more expensive real-model evaluation to use the same run contract;
- retain the existing saved-catalogue evidence while the CI migration is completed;
- avoid coupling the domain/application retrieval port to an evaluation vendor.

The design is consistent with current evaluation practice that separates datasets/tasks, subjects or configurations, trials/runs, and graders. Deterministic graders are preferred for exact properties, while pairwise/version comparisons operate over the same curated cases.

## Options considered

### 1. Keep the two execution paths

The existing paths are individually functional and require no migration.

This preserves duplicated scoring and invariant logic. Adding realistic benchmark cases, abstention policy, or additional retrievers would increase the divergence.

### 2. Make the retrieval-specific saved-run model universal

BM25, dense, and hybrid could all be adapted to the existing retrieval-specific `EvaluationStore`.

This preserves rich retrieval tables but makes a retrieval-specific persistence schema the platform-wide experiment contract, conflicting with the existing vendor-neutral `EvalDataset / EvalRun / EvalScore` architecture used for future generation and workflow evaluation.

### 3. Converge on the generic experiment runtime with a shared retrieval case grader

All retrieval strategies implement the existing `KnowledgeChunkRetriever` port. A shared retrieval case evaluator applies the same current/access/integrity/result-contract checks and retrieval metrics. Capability-specific executors adapt that result into `EvalObservation / EvalScore`, and `ExperimentRunner` produces the canonical run.

The saved-catalogue path can project approved cases into the same generic dataset shape while retaining its isolated per-case fixture preparation.

## Decision

Tropos uses option 3.

The canonical retrieval evaluation flow is:

```text
Versioned dataset
      ↓
Retrieval EvalCase
      ↓
KnowledgeChunkRetriever subject
(BM25 / dense / hybrid)
      ↓
shared retrieval case evaluation
├── expected evidence
├── authorized only
├── current only
├── evidence integrity
├── result contract
└── retrieval metrics
      ↓
EvalObservation + EvalScore
      ↓
ExperimentRunner
      ↓
EvalRun
      ↓
SQLiteExperimentStore / JSON interchange
      ↓
compare_runs / retrieval gate policy
```

`expected_evidence` is a benchmark outcome. Authorization, currentness, evidence integrity, and result-contract correctness are hard invariants.

A quality miss can therefore fail a benchmark case without being misclassified as a security/integrity violation. Real-model CI continues to block hard-invariant failures while exposing relevance/no-answer failures as benchmark evidence until abstention policy is calibrated.

The generic retrieval dataset fingerprint must bind to the knowledge corpus as well as the query labels. A run is not comparable merely because the query text is unchanged when the corpus has changed.

## Consequences

### Positive

- BM25, dense, and hybrid use one retrieval observation and scoring implementation.
- The enterprise-support benchmark emits the same `EvalRun` contract used by generic experiments.
- Model identifier, model revision, retrieval strategy, dependency lock, and code revision are recorded in run provenance.
- Generic JSON interchange and `SQLiteExperimentStore` can persist or compare runs without translating a custom real-model report.
- The PR regression gate can migrate from the saved-report bridge to direct generic runs without changing gate semantics.
- Future abstention, reranking, or retrieval strategies attach to one executor contract.

### Negative / trade-offs

- The existing retrieval-specific saved-run database remains as historical/diagnostic infrastructure during migration.
- The generic `EvalRun` output does not reproduce every relational table of the retrieval-specific store.
- The public enterprise-support holdout remains visible and is not a secret blind test set.
- Multiple query formulations derived from one support case are correlated observations; the unified runtime does not make them statistically independent.
- The current exact quality metrics remain knowledge-level until QE-108 adds chunk-level and graded relevance labels.

## Evidence

The convergence is implemented through:

- `tropos.evals.retrieval_case_evaluation` — one strategy-neutral observation implementation;
- `tropos.evals.retrieval_experiment` — generic retrieval dataset/executor adapters and hard-invariant semantics;
- `tropos.evals.run_io` — generic EvalRun JSON interchange;
- `tropos.evals.provenance` — code/dependency/runtime identity;
- enterprise-support retrieval projection bound to the knowledge-corpus fingerprint;
- the real-model workflow running BM25, dense, and hybrid through `ExperimentRunner`;
- tests covering metric/invariant separation, generic run round-trip, and catalogue snapshot binding.

The pull-request regression workflow is migrated in a separate follow-up change after these generic scripts exist on `main`, so the baseline worktree can execute the same runtime rather than relying on candidate-only code.

## Revisit when

Revisit this decision when:

- retrieval requires repeated stochastic trials rather than one deterministic query execution;
- a hosted evaluation system becomes the system of record and can preserve Tropos-owned run/dataset semantics through an adapter;
- QE-108 introduces chunk-level graded relevance that requires a new retrieval score contract;
- QE-109 adds calibrated abstention and changes the expected-empty execution semantics;
- production-derived cases require stricter data classification, access control, or externalized blind holdout storage.
