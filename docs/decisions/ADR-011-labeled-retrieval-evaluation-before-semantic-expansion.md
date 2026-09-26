# ADR-011: Establish a labeled retrieval evaluation baseline before semantic expansion

**Status:** Accepted
**Date:** 2026-09-26

## Context

Tropos now has a governed lexical retriever (`sqlite-fts5-bm25-v1`). The next retrieval decision is whether semantic/vector or hybrid retrieval is justified. Adding embeddings before measuring the lexical baseline would make it impossible to distinguish real quality gains from added architectural complexity.

Retrieval quality also cannot be inferred from unit-test coverage. Tropos needs labeled queries with expected evidence and explicit access-boundary cases.

## Options considered

1. Add vector retrieval immediately and judge quality manually.
2. Rely only on unit/integration tests around retrieval mechanics.
3. Add a versioned golden retrieval corpus, deterministic ranking metrics, and case-level access/no-answer checks before changing the retrieval strategy.

## Decision

Use option 3.

Retrieval Evaluation V1 uses a versioned synthetic corpus and computes:

- Recall@1, Recall@3, and Recall@5;
- Precision@5;
- mean reciprocal rank (MRR);
- no-answer accuracy for expected-empty cases.

V1 relevance labels are at `knowledge_id` level. Retrieved chunk results are deduplicated by `knowledge_id` for metric calculation while runtime retrieval continues to return individual chunks.

The corpus includes lexical cases, deliberately semantic/paraphrased cases, unrelated no-answer cases, and access-boundary cases. The retrieval strategy version is recorded in every report.

The evaluation harness does not add score-thresholding to the core retrieval contract. BM25 scores are strategy-native and not comparable to future vector or reranker scores.

## Consequences

### Positive

- Retrieval changes can be compared against an explicit baseline instead of intuition.
- Semantic failures become observable evidence for or against vector/hybrid retrieval.
- Access-boundary cases stay visible beside aggregate quality metrics.
- The same evaluator can compare future versioned retrievers through the existing `KnowledgeChunkRetriever` port.
- The core retrieval request remains strategy-neutral.

### Negative / trade-offs

- The V1 corpus is synthetic and small; it cannot support production accuracy claims.
- Knowledge-level labels are less precise than chunk-level or graded relevance labels.
- `Precision@5` has a low ceiling when each case has only one relevant document.
- No-answer accuracy currently means "returned no evidence"; it does not yet measure calibrated answerability confidence.
- A fixed regression snapshot must be intentionally updated when a new retrieval strategy is accepted.

## Evidence

- `tropos/evals/retrieval.py` contains the deterministic evaluator.
- `apps/api/evals/retrieval/golden_v1.json` contains the versioned seed corpus and labels.
- `tests/integration/evals/test_retrieval_golden_v1.py` executes ingestion plus retrieval against the corpus and records the lexical baseline.
- `docs/quality/EVAL_STRATEGY.md` documents metric semantics, limitations, and release use.

## Revisit when

Revisit this decision when:

- pilot/production-like queries are available for a held-out evaluation set;
- documents routinely contain multiple relevant chunks and chunk-level labels become necessary;
- graded relevance is needed for nDCG or reranking evaluation;
- vector or hybrid retrieval is introduced;
- score thresholds or answerability classification are proposed;
- workspace isolation changes the retrieval partitioning model.
