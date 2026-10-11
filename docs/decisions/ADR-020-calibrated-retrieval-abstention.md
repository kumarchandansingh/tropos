# ADR-020: Calibrate retrieval abstention outside the retrieval strategy

**Status:** Accepted  
**Date:** 2026-10-11

## Context

The first unified enterprise-support retrieval run exposed a clear quality gap.

On the development split, BM25, dense MPNet, and hybrid RRF each returned no evidence for only 1 of 12 expected-empty queries. At the same time, all three strategies passed authorization, currentness, evidence-integrity, and result-contract invariants.

The failure is therefore not access control. The retrievers are doing what ranking systems normally do: returning the best available authorized candidates even when those candidates are not sufficiently relevant to support an answer.

Tropos needs an explicit decision between:

```text
return ranked evidence
        or
abstain because evidence confidence is too low
```

Raw retrieval score cannot be treated as a universal confidence value. BM25 scores, cosine similarity, and RRF fusion scores have different scales and distributions. A threshold that is meaningful for one strategy is not portable to another.

Recent evidence-sufficiency research also distinguishes retrieval relevance from evidence sufficiency and reports that no single confidence signal is reliable across all RAG datasets. Tropos therefore treats score-threshold abstention as a calibrated baseline, not as the final definition of evidence sufficiency.

## Decision drivers and constraints

The abstention design must:

- reduce false answers on queries for which the corpus has no sufficient evidence;
- preserve a caller-defined minimum answerable Recall@5;
- choose policy parameters from development data only;
- evaluate the frozen policy on holdout/challenge data without recalibration;
- keep authorization/currentness/integrity as independent hard invariants;
- keep strategy-native scores out of the generic retrieval domain contract;
- record selected policy parameters and calibration provenance;
- avoid a global threshold shared across BM25, dense, and hybrid;
- remain simple enough to diagnose before adding model-based sufficiency verification.

## Options considered

### 1. Hard-code one global similarity threshold

This is operationally simple.

It is invalid across the current retrieval subjects because BM25, cosine, and RRF scores do not share one scale. A constant also has no evidence-based operating point.

### 2. Calibrate one top-score threshold per retrieval strategy

Use the highest returned strategy-native score as a confidence baseline. For each strategy, enumerate observed development thresholds, preserve an explicit answerable Recall@5 floor, then select the threshold with the lowest expected-empty unsupported-evidence-return rate.

This is deterministic, auditable, and cheap. It may generalize poorly because top score alone does not prove that evidence actually answers the question.

### 3. Add a learned/model-based evidence-sufficiency verifier immediately

A verifier could reason over the query and retrieved evidence jointly and potentially detect topical-but-insufficient evidence.

This adds model cost, calibration burden, new failure modes, and judge-quality questions before a simple baseline has been measured.

## Decision

Tropos uses option 2 as the V1 abstention baseline.

The decision remains outside the base retriever:

```text
query
  ↓
governed retriever
  ↓
ranked candidates + strategy-native scores
  ↓
calibrated abstention policy
  ├── score >= threshold → return candidates
  └── score < threshold  → return no evidence
```

The base `KnowledgeChunkRetriever` contract does not gain a generic confidence field.

Evaluation observations expose diagnostics separately:

- result count;
- top score;
- second score;
- top-to-second score margin;
- top-to-second score ratio.

V1 calibration uses **top score only**. Margin/ratio are recorded for diagnosis and future policy families; they are not combined into the selected V1 policy because the current benchmark is too small to justify fitting a more flexible decision surface.

The calibration operating point is supplied explicitly by the evaluation caller. The current workflow uses a minimum development answerable Recall@5 of **0.90**. This is a benchmark operating point, not a production SLA or universal threshold.

For each retrieval strategy:

1. run the raw retriever on development data;
2. enumerate finite thresholds derived from observed development top scores;
3. keep only thresholds meeting the required answerable Recall@5 floor;
4. minimize expected-empty unsupported-evidence-return rate;
5. break ties by higher answerable Recall@5, then the less aggressive threshold;
6. freeze the selected threshold;
7. run the same frozen policy on development, holdout, and challenge splits;
8. record the policy in subject configuration and run provenance.

Holdout/challenge results never select or alter the threshold.

## Consequences

### Positive

- Abstention becomes an explicit, measurable product decision instead of an implicit side effect of retrieval.
- Unsupported-evidence-return rate, false-abstention rate, and retained answerable recall can be discussed at one operating point.
- BM25, dense, and hybrid receive independent thresholds appropriate to their score scales.
- Policy selection is deterministic and reproducible.
- The selected threshold is recorded with dataset identity, strategy version, and run provenance.
- Access-control failures remain distinguishable from relevance abstention.
- The wrapper can be replaced later without changing the core retriever interface.

### Negative / trade-offs

- The current development set is small and contains correlated query variants.
- Top score is only a weak proxy for evidence sufficiency.
- BM25 score magnitude is query/corpus dependent.
- RRF scores are compressed by the fusion formula and may offer poor confidence separation.
- A threshold tuned on public synthetic development data can overfit.
- The 0.90 recall floor is an explicit evaluation choice, not evidence of the correct production risk tolerance.
- The V1 policy does not inspect whether multiple passages jointly cover the complete information need.

## Evidence

Implementation is located in:

- `tropos.evals.abstention` — calibration, policy evaluation, and thresholded retriever wrapper;
- `tropos.evals.retrieval_case_evaluation` — strategy-native diagnostic capture;
- `evaluate_enterprise_support_retrieval.py` — development calibration followed by holdout/challenge verification;
- `hybrid-real-eval.yml` — explicit `--minimum-answerable-recall 0.90` operating point.

The resulting evidence report records raw retrieval performance and abstention-applied performance separately.

External references:

- Joren et al. (Google Research, ICLR 2025), *Sufficient Context: A New Lens on Retrieval Augmented Generation Systems*: <https://research.google/pubs/sufficient-context-a-new-lens-on-retrieval-augmented-generation-systems/>
- LangChain, *Deconstructing RAG*: <https://www.langchain.com/blog/deconstructing-rag>

## Revisit when

Revisit this decision when:

- QE-108 provides enough independent scenarios to fit and validate richer policies;
- score margin or cross-retriever agreement materially improves holdout risk;
- top-score thresholds fail to generalize across corpus changes;
- generation requires set-level evidence sufficiency rather than candidate relevance;
- a calibrated local verifier or model judge demonstrates materially better false-answer/coverage trade-offs;
- production risk tolerance establishes a different answerable-recall or unsupported-evidence-return operating point.
