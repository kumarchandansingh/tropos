# RAG Architecture

Tropos is being designed toward retrieval-augmented decision support, but the repository is **not yet a full RAG system**. The correct way to understand the current state is to separate the implemented evidence foundation from the planned retrieval and reasoning layers.

## Target RAG pipeline

```mermaid
flowchart LR
    S[Source knowledge]
    --> N[Normalize]
    --> C[Chunk]
    --> P[Persist]
    --> I[Index]
    --> R[Retrieve]
    --> K[Rank / select]
    --> A[Assess coverage]
    --> D[Decide knowledge action]
    --> G[Optional AI-assisted explanation / drafting]
    --> E[Evaluate]
```

## What exists today

```mermaid
flowchart TB
    subgraph Implemented[IMPLEMENTED]
      R1[RawKnowledgeRecord + fingerprint]
      AP[AccessPolicy]
      KD[KnowledgeDocument]
      CH[DeterministicKnowledgeChunker]
      KC[KnowledgeChunk + invariants]
      PS[KnowledgeCorpusStore port]
      SQ[(SQLite canonical corpus)]
      DI[Knowledge decision policy]
      OR[EvaluateCaseClosure orchestration]
      R1 --> KD --> CH --> KC --> PS --> SQ
      AP --> KD
      OR --> DI
    end

    subgraph Contract[CONTRACT ONLY]
      RET[KnowledgeRetriever]
      COV[KnowledgeCoverageEvaluator]
      STORE[KnowledgeDecisionStore]
    end

    subgraph Planned[PLANNED NEXT]
      FTS[SQLite FTS5 / BM25 lexical retrieval]
      ACL[tenant/group filtering]
      HIT[chunk-level RetrievalHit / evidence bundle]
      CE[Concrete coverage evaluator]
      DS[(Decision persistence)]
      EV[Retrieval + product evaluations]
      SQ --> FTS --> ACL --> HIT --> CE
      DS --> EV
    end

    subgraph Deferred[DEFERRED UNTIL BASELINE EXISTS]
      EMB[Embeddings / vector retrieval]
      HYB[Hybrid retrieval / reranking]
      LLM[LLM-assisted reasoning / drafting]
    end

    RET -. future adapter .-> FTS
    COV -. future adapter .-> CE
    STORE -. future adapter .-> DS
    FTS -. evidence of semantic-recall gap .-> EMB
    EMB --> HYB
    CE -. after measurable baseline .-> LLM
```

## What changed with persistence

The pipeline now has an executable boundary between governed chunks and future retrieval:

```mermaid
flowchart LR
    KC[Validated KnowledgeChunk set]
    --> Port[KnowledgeCorpusStore]
    --> SQL[(SQLite canonical corpus)]
    --> Next[FTS5 index / retriever<br/>next slice]
```

The persistence adapter is deliberately **not** called a retriever. It stores and reconstructs exact governed evidence. Retrieval will be a separate adapter with its own ranking, permission filtering and evaluation behavior.

## Why the stages are separate

A fluent final answer can hide failures earlier in the pipeline. Tropos therefore treats persistence, retrieval, coverage, decision policy and generation as separate quality surfaces.

| Stage | Question | Typical failure |
| --- | --- | --- |
| Normalization | Did source content become a correct canonical document? | lost fields / corrupted text / lost ACL |
| Chunking | Is the evidence unit faithful and reproducible? | fragmentation / citation drift |
| Persistence | Can canonical evidence be reconstructed by stable identity? | stale or partial snapshot |
| Retrieval | Did we fetch relevant candidates? | low recall |
| Ranking | Are the useful candidates near the top? | noisy top-k |
| Coverage | Is existing knowledge enough to resolve the case? | wrong `CREATE/IMPROVE/REUSE` input |
| Decision policy | Given validated facts, is the action deterministic? | hidden policy drift |
| Generation | Is any explanation/draft grounded in evidence? | hallucination |
| Evaluation | Did a change improve behavior without serious regressions? | aggregate score hides failures |

## Retrieval baseline: lexical before vector

The next retrieval strategy remains intentionally incremental.

```mermaid
flowchart LR
    Chunk[Governed chunks]
    --> Persist[(SQLite canonical corpus)]
    --> FTS[SQLite FTS5 / BM25 baseline]
    --> ACL[tenant/group filter]
    --> Dataset[Build retrieval eval set]
    --> Measure[Measure recall / precision / ranking]
    --> Gap{Material semantic-recall gap?}
    Gap -- no --> Keep[Keep simpler retrieval]
    Gap -- yes --> Embed[Add embeddings]
    Embed --> Hybrid[Compare hybrid vs baseline]
```

This is not an anti-vector position. It is an experimental-design choice: add complexity only after a baseline can show what problem the complexity solves.

## Access filtering belongs before model reasoning

Tropos already makes unresolved access non-indexable and now persists tenant/scope/group metadata beside each chunk. Future retrieval must preserve that principle:

```mermaid
flowchart LR
    Query[Case/query]
    --> Search[FTS5 candidate search]
    --> Policy[Apply tenant/group access policy]
    --> Evidence[Allowed evidence only]
    --> Coverage[Coverage evaluation]
    --> Model[Optional model reasoning]
```

A model should never be used as the mechanism for deciding whether retrieved evidence was authorized in the first place.

## Planned retrieval contract

The current domain has `RetrievedKnowledge(document, score)`, while the chunk-level retrieval path will need a richer evidence contract carrying exact chunk IDs and provenance.

A target shape is conceptually:

```text
RetrievalHit
├── chunk_id
├── knowledge_id
├── score
├── rank
├── source identity / version
├── exact text offsets
├── access policy reference
└── retrieval strategy/version
```

This is **PLANNED**, not implemented. The purpose is to keep the retrieval representation explicitly tied to the governed `KnowledgeChunk`.

## Coverage is its own decision stage

Retrieval answers *what might be relevant*. Coverage answers *whether the evidence is sufficient*.

```mermaid
flowchart TD
    R[Retrieved evidence]
    --> C{Coverage assessment}
    C -->|NONE| Create[CREATE]
    C -->|PARTIAL| Improve[IMPROVE]
    C -->|SUFFICIENT| Reuse[REUSE]
```

Conflating retrieval score with coverage would be a design error. A highly similar article can still be incomplete; several moderately ranked chunks can collectively provide sufficient coverage.

## LLM role — deliberately downstream

When an LLM is introduced, Tropos should use it for bounded tasks behind validated contracts, for example:

- semantic coverage assessment after evidence retrieval;
- evidence-backed rationale;
- suggested article improvement/draft;
- reviewer assistance.

The LLM should not own the stable action vocabulary or bypass access/provenance controls.

```mermaid
flowchart LR
    Evidence[Validated evidence]
    --> Prompt[Versioned prompt + contract]
    --> LLM[Model]
    --> Parse[Structured output validation]
    --> Policy[Governed application/domain decision]
```

## RAG change isolation

To diagnose regressions, avoid changing chunking, retrieval, embedding model, reranker and prompt in one experiment.

```mermaid
flowchart LR
    Baseline[Known baseline]
    --> One[Change one material variable]
    --> Eval[Run applicable eval suite]
    --> Compare[Compare aggregate + case regressions]
    --> Decision{Accept?}
    Decision -- yes --> New[New baseline]
    Decision -- no --> Revert[Reject / revise]
```

## Release consequence

Once retrieval or model reasoning becomes executable product behavior, a green software CI run will be necessary but not sufficient. Relevant retrieval/AI eval gates must also pass before release eligibility.

See `../quality/EVAL_STRATEGY.md` for the evaluation model.
