# Enterprise support retrieval evidence

## Purpose

This document records measured retrieval evidence from the realistic enterprise-support development benchmark. It separates observed test-set behavior from product or production claims.

The benchmark and evaluation runtime are described in:

- [Enterprise support benchmark V1](ENTERPRISE_SUPPORT_BENCHMARK.md)
- [Evaluation strategy](EVAL_STRATEGY.md)
- [ADR-019: Unified retrieval evaluation runtime](../decisions/ADR-019-unified-retrieval-evaluation-runtime.md)

## Recorded run

The first unified real-model comparison was produced during PR #88 validation on 2026-10-11.

| Field | Recorded value |
| --- | --- |
| Dataset | `tropos-enterprise-support-benchmark-retrieval` |
| Dataset version | `1.0-development` |
| Dataset fingerprint | `e7994a43dc4907a189f43c3a272cbfdcfa79879613ee9d64704aaae4dd17c98e` |
| Cases | 24 |
| Answerable cases | 12 |
| Expected-empty cases | 12 |
| Embedding model | `sentence-transformers/all-mpnet-base-v2` |
| Model revision | `e8c3b32edf5434bc2275fc9bab85f82640a19130` |
| sentence-transformers | `6.1.0` |
| Dense search | exact cosine |
| Hybrid | Reciprocal Rank Fusion (RRF), k=60 |
| Retrieval cutoff | 5 |
| Evaluator | retrieval deterministic v2 |

The GitHub Actions evidence for that validation run passed all retrieval hard invariants. The recorded workflow artifact is reproducible from the same versioned benchmark, pinned model revision, dependency lock, and evaluation code.

## Results

| Metric | BM25 | Dense MPNet | Hybrid RRF |
| --- | ---: | ---: | ---: |
| Recall@1 | 0.458 | **0.625** | **0.625** |
| Recall@3 | 0.833 | **1.000** | 0.917 |
| Recall@5 | 0.917 | **1.000** | **1.000** |
| Precision@5 | 0.233 | **0.250** | **0.250** |
| Mean reciprocal rank | 0.750 | **0.861** | 0.850 |
| No-answer accuracy | **0.083** | **0.083** | **0.083** |
| Passed cases | 12 / 24 | 13 / 24 | 13 / 24 |
| Hard-invariant failures | 0 | 0 | 0 |

These are development-set results. They are not estimates of enterprise or production accuracy.

### Paired movement from BM25

The same 24 cases were executed against all three subjects.

| Metric | Dense minus BM25 | Hybrid minus BM25 |
| --- | ---: | ---: |
| Recall@1 | +0.167 | +0.167 |
| Recall@3 | +0.167 | +0.083 |
| Recall@5 | +0.083 | +0.083 |
| Precision@5 | +0.017 | +0.017 |
| Mean reciprocal rank | +0.111 | +0.100 |
| No-answer accuracy | 0.000 | 0.000 |

Dense and hybrid each converted one previously failing answerable case to a pass without creating an answerable-case regression in this run. With only 12 answerable paired observations, Tropos deliberately does not report bootstrap confidence intervals for these comparisons.

## What the evidence says

### Semantic retrieval improves answerable retrieval on this set

Dense MPNet recovered all expected knowledge within the top three for the 12 answerable development queries. Hybrid reached all expected knowledge within the top five and improved ranking over BM25, but dense slightly outperformed hybrid at Recall@3 and mean reciprocal rank in this run.

The evidence therefore does not justify treating hybrid as automatically superior to dense retrieval. The benchmark should continue to compare both subjects.

### Abstention is the dominant measured failure

All three strategies returned no evidence for only **1 of 12** expected-empty cases.

The one naturally empty case is strongly governed by candidate availability; most other unsupported or CREATE scenarios still return the nearest authorized documents. This is not an authorization leak: the hard access/currentness/integrity checks all passed. It is a relevance and abstention problem.

The measured implication is direct:

```text
retrieval candidate generation works
        ↓
answerable recall improves with dense/hybrid
        ↓
but nearest authorized evidence is still returned
for unsupported questions
        ↓
calibrated abstention is required before
retrieval output can safely drive generation
```

This is the evidence basis for QE-109.

### Hard invariants remain separate from quality

The run recorded zero failures for:

- authorization;
- current-version filtering;
- evidence integrity;
- retrieval result-contract semantics.

A low no-answer score therefore does not weaken the security conclusion, and passing security checks does not make the retrieval quality acceptable. They are different quality dimensions.

## Limitations

The result should be interpreted narrowly:

- only 12 answerable and 12 expected-empty development queries were measured;
- multiple query formulations come from the same underlying support case and are therefore correlated;
- the development set is public and may be inspected during implementation;
- labels remain knowledge-level rather than chunk-level graded relevance;
- no calibrated abstention policy is applied;
- latency/cost comparisons are not yet decision metrics;
- the run evaluates retrieval, not generated Knowledge Articles or user outcomes.

QE-108 remains responsible for larger independent scenario populations, chunk-level/graded labels, stronger holdout mechanics, and uncertainty reporting. QE-109 owns abstention calibration and false-answer risk.

## Decision implication

No retrieval strategy is promoted as the production default from this evidence.

Dense and hybrid are stronger candidates than BM25 for answerable semantic retrieval on the current development set. The next quality decision is to calibrate **when to return no evidence**, then compare the strategies at a defined false-answer/recall operating point rather than selecting the subject with the highest recall alone.
