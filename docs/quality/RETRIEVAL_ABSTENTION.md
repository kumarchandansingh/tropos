# Retrieval abstention calibration

## Purpose

Retrieval ranking answers:

> Which eligible evidence is closest to this query?

Abstention answers a different question:

> Is the available evidence strong enough to return at all?

Tropos keeps these decisions separate.

The first realistic enterprise-support benchmark showed that BM25, dense MPNet, and hybrid RRF could retrieve useful evidence for answerable queries but each abstained correctly on only 1 of 12 expected-empty development queries. This document defines the V1 calibration method used to reduce that false-answer risk.

## Product boundary

```text
query + access context
        ↓
governed retriever
        ↓
ranked candidates
        ↓
strategy-native score diagnostics
        ↓
calibrated abstention policy
   ┌───────────────┴───────────────┐
   ↓                               ↓
return candidates               abstain
   ↓                               ↓
possible downstream           no evidence
generation
```

Abstention does not override tenant/group authorization. Authorization is applied inside retrieval before the abstention decision sees candidates.

## Diagnostics

Every retrieval observation now records the following diagnostics separately from benchmark scores:

| Diagnostic | Meaning |
| --- | --- |
| result count | Number of chunks returned before abstention |
| top score | Strategy-native score of rank 1 |
| second score | Strategy-native score of rank 2 |
| top-score margin | top score minus second score |
| top-score ratio | top score divided by second score when defined |

The values are not comparable across strategies.

- BM25 uses its transformed FTS5 ranking score.
- Dense MPNet uses cosine similarity.
- Hybrid uses Reciprocal Rank Fusion score.

A BM25 score of 4.0 and a dense score of 0.4 have no shared meaning.

## V1 calibration policy

V1 uses the **top score** only.

For one retrieval strategy, the development run supplies:

```text
answerable cases
├── retrieval score
└── Recall@5 before abstention

expected-empty cases
└── retrieval score
```

The evaluator enumerates thresholds derived from the observed development top scores.

For each threshold:

```text
top score >= threshold
        ↓
return evidence

top score < threshold
        ↓
abstain
```

A naturally empty retrieval result always abstains.

## Selection objective

The calibration caller supplies a minimum answerable Recall@5.

The current automated workflow passes:

```text
minimum answerable Recall@5 = 0.90
```

This means the policy may reject some weak retrievals, but it cannot be selected if doing so drives the development-set answerable Recall@5 below 0.90.

Among thresholds that satisfy that floor, calibration chooses:

1. lowest expected-empty false-answer rate;
2. then highest answerable Recall@5;
3. then the lower threshold when outcomes are tied.

The 0.90 value is an explicit experiment operating point, not a production SLA.

## Metrics after abstention

### Answerable Recall@5

For answerable cases:

- if the policy returns evidence, the normal Recall@5 contributes;
- if the policy abstains, that case contributes zero.

This captures both retrieval failure and over-abstention.

### Answerable coverage

Fraction of answerable cases for which the policy returns evidence.

Coverage is useful beside recall because an answerable case can be returned while still missing the labelled evidence.

### No-answer accuracy

For expected-empty cases:

```text
correct abstentions
──────────────────
expected-empty cases
```

### False-answer rate

```text
expected-empty cases where evidence is returned
───────────────────────────────────────────────
expected-empty cases
```

For the current binary abstention definition:

```text
false-answer rate = 1 - no-answer accuracy
```

The term refers to retrieval supplying evidence when the benchmark says no sufficient evidence exists. It does not mean an LLM has already generated a false statement.

## Development and validation separation

Threshold selection is allowed only on the development split.

```text
development
    ↓
select threshold
    ↓
freeze policy
   ┌────────────┬────────────┐
   ↓            ↓            ↓
development   holdout     challenge
measure       verify      stress
```

The calibration code rejects a run whose provenance does not identify it as development data.

Holdout/challenge runs contain the frozen policy in both subject configuration and run provenance. They can measure generalization but cannot alter the threshold.

Because Tropos is a public repository, the holdout split is visible. It is therefore a locked-by-convention validation set rather than a secret blind benchmark.

## Why V1 does not use score margin yet

A top-score margin can help distinguish a clear winner from an ambiguous ranking. The current dataset is too small to fit a two-dimensional top-score + margin policy without materially increasing overfitting risk.

Tropos records the margin now so later benchmark versions can test whether it improves holdout performance.

## Why a score threshold is not the final sufficiency model

A high retrieval score can mean:

- the passage is topically similar;
- the passage contains the same product/error vocabulary;
- the passage is the closest available item.

It does not prove:

- the passage contains the facts required to answer;
- all parts of a multi-part question are covered;
- conflicting evidence has been resolved;
- several passages jointly provide sufficient evidence.

Recent RAG evidence-sufficiency research reports the same distinction and finds that no single retrieval confidence signal works reliably across all datasets.

V1 therefore establishes a measurable baseline before adding a more complex evidence-sufficiency verifier.

## Quality interpretation

A useful retrieval release view becomes:

| Dimension | Question |
| --- | --- |
| Recall@K | When evidence exists, did we retrieve it? |
| Ranking / MRR | How early did useful evidence appear? |
| False-answer rate | When evidence did not exist, did we still return something? |
| Answerable coverage | How often did abstention allow answerable requests through? |
| Hard invariants | Was every returned item authorized, current, intact, and contract-valid? |

No one metric substitutes for another.

## Current limitations

- 12 answerable + 12 expected-empty development queries are too few for a production threshold claim.
- Multiple queries are derived from the same underlying support case.
- Score distributions can drift when corpus composition changes.
- RRF top scores are structurally compressed.
- No learned evidence-sufficiency verifier is implemented.
- No generated-answer correctness is measured by this policy.

QE-108 remains responsible for stronger benchmark scale and independence. QE-109 owns the abstention operating point and false-answer risk.
