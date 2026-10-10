# Evaluation contracts

## Purpose

Tropos owns the meaning of evaluation data and quality outcomes. Hosted tools may execute, trace, compare, and visualize runs later, but they do not define what a Tropos case, golden dataset, score, or release-relevant observation means.

The reusable contracts live in `tropos.evals.contracts`.

## Contract model

```text
EvalDataset
├── dataset_id
├── version
├── capability
├── split
└── EvalCase[]
     ├── component / end-to-end scope
     ├── candidate / approved state
     ├── synthetic / human / production-derived origin
     ├── inputs
     ├── expected behavior
     └── stable fingerprint

EvalRun
├── dataset reference
├── evaluated subject/configuration
├── run provenance
├── baseline_run_id (optional)
├── observations
└── run lifecycle

EvalObservation
├── case_id
├── state
├── actual output
├── EvalScore[]
├── duration
└── safe error type

EvalScore
├── metric
├── value
├── deterministic / model-judge / human source
├── evaluator identity/version
├── pass/fail interpretation
└── optional rationale
```

## Golden data lifecycle

LLM-generated examples are not automatically golden data.

```text
Synthetic or collected candidate
        ↓
curation / review
        ↓
EvalApproval.APPROVED
        ↓
versioned dataset snapshot
        ↓
experiment / regression execution
```

A change from candidate to approved changes the case and dataset fingerprint. The same is true for a change in expected behavior. This makes the approved definition part of the versioned product specification rather than invisible metadata.

Datasets declare one of three intended splits:

- `development` — used repeatedly while prompts, models, retrieval, or logic are being tuned;
- `holdout` — reserved for less-frequent release confidence checks;
- `challenge` — edge, adversarial, policy, ambiguity, conflict, and other deliberately difficult scenarios.

## Fingerprints and identity

Canonical JSON plus SHA-256 provides deterministic fingerprints for cases, datasets, and evaluated configuration. JSON object key order does not change a fingerprint; behaviorally meaningful content does.

A dataset ID/version remains the human-facing identity. Its fingerprint represents the exact snapshot. Persistence code must reject reusing one ID/version for different content, matching the protection already implemented in the retrieval evaluation store.

## Run provenance versus content evidence

Run provenance records how an experiment was produced: code revision, dependency digest, runtime metadata, model/prompt/retrieval configuration, and similar processing context.

It is intentionally separate from content evidence such as `EvidenceRef`. Provenance answers "how was this output produced?" Evidence answers "what source supports this claim?" They must not be conflated.

## Score sources

A score records its source explicitly:

| Source | Appropriate use |
| --- | --- |
| deterministic | exact workflow/action checks, citation identity, required sections, policy assertions |
| model judge | semantic qualities that cannot be fully expressed as deterministic rules |
| human | expert adjudication, calibration, contested or high-risk cases |

Judge or human scores still require a stable evaluator identity/version so comparisons remain explainable.

## Component and end-to-end evaluation

`EvalScope.COMPONENT` isolates one boundary such as classification, retrieval, Knowledge Article generation, or NBA selection.

`EvalScope.END_TO_END` evaluates the whole user journey. Component evals explain why a system failed; end-to-end evals establish whether the product outcome succeeded.

## Relationship to the existing retrieval evaluator

The existing retrieval catalogue, runner, SQLite run store, and reports remain valid and executable. They are specialized retrieval infrastructure that predates the generic contracts.

This slice does not rewrite them. It captures the reusable concepts that later evaluation-runtime work can use across Resolve, Training, and retrieval. Migration should preserve the existing retrieval evidence and regression baseline rather than force a risky one-step refactor.

## Vendor boundary

```text
Tropos-owned contracts
        ↓
experiment / tracing adapter
        ↓
LangSmith | Langfuse | Phoenix | other
```

Tropos remains the source of truth for:

- approved golden cases;
- expected behavior;
- evaluator semantics;
- run/configuration identity;
- score meaning;
- release gates.

A hosted platform may receive synchronized datasets, observations, traces, and scores for execution or visualization. Removing that platform must not require changes to capability/domain code or destroy the canonical eval definitions.

## Current experiment implementation

QE-103 now implements the generic experiment layer over these contracts:

- `ExperimentRunner` executes one immutable dataset snapshot against one `EvalSubject`;
- capability-owned `EvalCaseExecutor` implementations return terminal `EvalObservation` records;
- `SQLiteExperimentStore` persists immutable run, observation, and score evidence;
- `compare_runs` performs case-level baseline-versus-candidate classification;
- shared numeric dimensions are compared pairwise with optional paired-bootstrap uncertainty;
- gate policy separates hard invariants from aggregate decision metrics.

See [Evaluation experiments and regression comparison](EVALUATION_EXPERIMENTS.md).

## Current exclusions

The generic experiment layer still does not add:

- LangSmith/Langfuse/Phoenix adapters;
- LLM-as-judge implementation or calibration;
- human review UI;
- production PR/nightly/release thresholds;
- a locked holdout benchmark;
- calibrated retrieval abstention.

Those remain subsequent backlog slices.
