# Evaluation product model

## Purpose

This document separates two questions that were previously mixed together:

1. **What product behavior are we trying to make trustworthy?**
2. **How do we execute, score, compare, and gate that behavior?**

The first is the **product quality model**. The second is the **evaluation runtime**.

Tropos uses evaluation as an umbrella term. Software tests, invariant checks, benchmarks, model evaluations, and product outcomes are different assurance mechanisms and must be reported separately.

## Canonical terminology

| Term | Meaning in Tropos |
| --- | --- |
| Software test | A unit, integration, or contract test of deterministic code behavior |
| Invariant | A property that must never be violated, such as authorization or current-version integrity |
| Benchmark | A fixed labelled set used to measure quality, such as retrieval Recall@K or MRR |
| Model eval | An evaluation in which a real model produces the output being judged |
| Product evaluation | Measurement of the user or workflow outcome in the real product |
| Grader | Code, model, or human logic that judges one output or one dimension of it |
| Eval case | One scenario with inputs and expected behavior |
| Trial | One execution of one case; multiple trials matter when the subject is stochastic |
| Run | A complete execution of a dataset against one subject/configuration |
| Subject | The system or configuration being evaluated: retriever, prompt, model, workflow, or combination |
| Baseline | The reference subject/run used for comparison |
| Candidate | The proposed subject/run used for comparison |
| Gate | A rule that decides whether evidence is sufficient to allow a change to proceed |

A **check** is a single assertion. A grader may contain multiple checks. An invariant is not a benchmark metric: one invariant failure is a defect even when average quality improves.

## Product quality map

Start with the product behavior, not with the evaluation framework.

```text
Resolved case / governed source knowledge
                ↓
            Retrieval
                ↓
       Selected evidence
                ↓
    Knowledge Article generation
                ↓
      Generated artifact
                ↓
 future agent / user outcome
```

Different assurance mechanisms attach to different product boundaries:

```text
Retrieval
├── software tests
├── invariant checks
└── retrieval benchmark

Knowledge Article generation
├── software tests
├── deterministic artifact graders
└── real model evals

Future agent / user outcome
└── product evaluation
```

### Retrieval

The product question is: **did Tropos return the right current, authorized evidence for this query?**

- Software tests verify retriever and access-control code in isolation.
- Invariant checks verify assembled-system properties such as authorization, currentness, evidence integrity, and result-contract correctness.
- Benchmarks measure quality such as Recall@K, ranking, and no-answer behavior.

Security/currentness failures are not “low recall”. They are invariant failures and are reported separately from benchmark quality.

### Knowledge Article generation

The product question is: **did Tropos turn selected evidence into a useful operational artifact without inventing or distorting information?**

Deterministic graders can check exact properties such as:

- required structure;
- stable evidence-reference alignment;
- typed gaps for missing or conflicting information;
- absence of explicitly forbidden actions.

Those graders become a **model eval** only when a real generator produces the draft under test. Testing the grader against hand-authored drafts proves the grader, not the model.

Semantic groundedness or quality that cannot be expressed reliably in code may later use a calibrated model grader and human-labelled reference examples.

### Product outcome

The eventual product question is: **did the recommendation or knowledge artifact help the agent/user resolve the real task?**

This requires production or human workflow evidence such as acceptance, edits, resolution success, time-to-resolution, or reviewer outcome. It is not implemented as a Tropos evaluation signal today.

## Evaluation runtime

Once the product behavior and success criteria are defined, the reusable runtime is:

```text
Dataset
   ↓
Eval case
   ↓
Subject under test
   ↓
Trial / execution
   ↓
Output
   ↓
Grader(s)
   ↓
Observation + scores
   ↓
Run
   ↓
Baseline vs candidate comparison
   ↓
Gate
```

### Four questions before adding any evaluation

For every proposed case, answer these before implementation:

1. **What is the input?**
2. **What subject/system is actually under test?**
3. **What output is produced?**
4. **Who or what judges that output?**

If those four answers are unclear, the test/eval definition is not ready.

## Current Tropos mapping

| Product boundary | Current subject | Current judge | Current status |
| --- | --- | --- | --- |
| Retrieval | BM25 in PR gate | deterministic invariants + Recall/MRR/no-answer metrics | implemented |
| Retrieval | BM25, dense MPNet, hybrid RRF nightly | retrieval metrics + explicit authorization-leak gate | implemented, separate path |
| Knowledge Article artifact | hand-authored `KnowledgeArticleDraft` fixtures | deterministic article grader | grader validation only |
| Knowledge Article real model output | generator + real model | not wired into generic run path | not yet implemented |
| Product outcome | agent/user workflow | human/production outcome | not yet implemented |

## Current architecture seam

Tropos currently has two retrieval-evaluation execution paths:

```text
Saved retrieval / PR path
catalogue → execution.observe → EvaluationStore
        → regression bridge → generic EvalRun → compare_runs

Real-model retrieval path
golden_v1 → evaluate_retrieval → RetrievalEvalReport
        → special access gate → JSON report
```

The generic contracts and `ExperimentRunner` already provide the intended cross-capability model:

```text
EvalDataset + EvalSubject + provenance
              ↓
       EvalCaseExecutor
              ↓
       EvalObservation
              ↓
           EvalRun
              ↓
       compare_runs / gate
```

The next implementation cleanup should converge retrieval onto that model rather than add a third execution style.

## Design rules for the next builds

- Keep invariant checks separate from benchmark metrics in reports and gate semantics.
- Run shared retrieval invariants against every retriever that can ship.
- Prefer one execution/result/persistence shape across BM25, dense, and hybrid retrieval.
- Grow the retrieval benchmark only after the execution path is clear.
- Introduce repeated trials when a real stochastic model is the subject.
- Prefer deterministic graders where the desired behavior is exact.
- Use model graders only for semantic qualities that code cannot judge reliably, and calibrate them against human-labelled examples before gating.
- Keep development data separate from locked holdout evidence.
- Treat product-outcome evaluation as a later layer, not as a proxy for component quality.

## Relationship to implementation documents

- [Evaluation contracts](EVALUATION_CONTRACTS.md) defines the reusable data contracts.
- [Evaluation experiments](EVALUATION_EXPERIMENTS.md) defines run/comparison/gate behavior.
- [Evaluation runs](EVALUATION_RUNS.md) documents saved retrieval execution.
- [RAG architecture](RAG_ARCHITECTURE.md) owns retrieval runtime architecture.
- [Evaluation strategy](../quality/EVAL_STRATEGY.md) owns quality strategy and benchmark maturity.
