# ADR-002: Governed evidence model and deterministic chunking first

**Status:** Accepted  
**Date:** 2026-09-20  
**Clarified:** 2026-09-21 by ADR-004

## Context

Tropos will eventually retrieve knowledge to support `REUSE`, `IMPROVE`, `CREATE`, and `NO_ACTION` decisions. Retrieval quality will depend on chunking, indexing and later semantic search. If the system starts with opaque vector-store rows or random chunk identities, it becomes difficult to prove what exact canonical content a recommendation relied on, whether access policy was preserved, or whether a later processing change altered evidence boundaries.

The system therefore needs a canonical evidence unit before introducing semantic retrieval.

ADR-004 later clarified the identity immediately upstream of chunking: **canonical content identity is not the same as raw/source-envelope identity.** A presentation-only source change must not randomize canonical chunk identity.

## Options considered

### 1. Store only raw documents and let each retriever chunk independently

Simple initially, but chunk identity and evidence boundaries become retriever-specific and hard to reproduce.

### 2. Store only vector/index representations

Fast for a RAG prototype, but weak for provenance, access governance and exact citation reconstruction.

### 3. Canonical governed chunks with deterministic generation

Create a first-class `KnowledgeChunk` with exact canonical offsets, fingerprints, access policy and strategy lineage, then treat lexical/vector indexes as secondary representations.

## Decision

Tropos treats `KnowledgeChunk` as the canonical retrieval evidence unit and establishes a **deterministic, lossless chunking baseline before semantic/vector retrieval**.

A valid chunk set must preserve:

- exact canonical-document text coverage;
- stable identity for the same canonical content and processing strategies;
- source system/record/version provenance;
- ingestion and normalized-content lineage;
- exact chunk-content fingerprint;
- inherited access policy;
- normalization and chunking strategy versions;
- contiguous, gap-free, overlap-free ordering.

Embeddings and search indexes, when introduced, represent chunks; they do not replace the canonical evidence model.

### Chunk identity clarification

After ADR-004, `chunk_id` is derived from:

```text
knowledge_id
+ normalized_content_fingerprint
+ normalization_strategy_version
+ chunking_strategy_version
+ start_offset
+ end_offset
+ exact_chunk_text_fingerprint
```

`source_version` and `ingestion_fingerprint` remain provenance but are intentionally excluded from chunk identity. This prevents formatting/source-version churn from creating unrelated chunk IDs when canonical content is unchanged.

## Rationale

Tropos is a governed knowledge system, not merely a question-answering demo. Reproducible evidence is therefore a product requirement.

The deterministic baseline also creates a controlled starting point for later retrieval experiments. If semantic retrieval is added, the team can measure improvement without simultaneously changing the evidence model.

## Consequences

### Positive

- exact evidence can be traced to canonical source ranges and upstream lineage;
- reprocessing the same canonical content/strategies yields stable identities;
- irrelevant upstream formatting/version churn does not force chunk-ID churn;
- access semantics survive chunking;
- later search technologies remain replaceable;
- retrieval/citation regressions can be investigated at chunk level;
- normalization and chunking strategy changes are separately observable.

### Negative / trade-offs

- more metadata per chunk;
- deterministic character/structural chunking may not be semantically optimal;
- canonical chunk persistence must later handle source/content/access lifecycle explicitly;
- changing either normalization or chunking strategy can require reprocessing and evaluation.

## Evidence

Implemented in current paths:

- `apps/api/src/tropos/core/domain/access.py`
- `apps/api/src/tropos/core/domain/knowledge.py`
- `apps/api/src/tropos/core/domain/knowledge_chunk.py`
- `apps/api/src/tropos/core/application/ingestion/normalization.py`
- `apps/api/src/tropos/core/application/ports/chunking.py`
- `apps/api/src/tropos/core/adapters/chunking/deterministic.py`
- corresponding core normalization/domain/chunking unit tests.

`validate_chunk_set` proves full contiguous canonical-text coverage and metadata consistency. `DeterministicKnowledgeChunker` derives stable chunk IDs from canonical content identity, processing strategy versions, offsets and exact text identity.

## Revisit when

Revisit the chunking algorithm when retrieval evaluation demonstrates a measurable failure that the current structural/character baseline cannot address.

Possible future alternatives include semantic segmentation, heading-aware/content-type-specific chunkers, but any replacement must preserve the governed evidence contract and be evaluated against the existing baseline.
