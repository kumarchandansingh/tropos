# ADR-002: Governed evidence model and deterministic chunking first

**Status:** Accepted  
**Date:** 2026-09-20

## Context

Tropos will eventually retrieve knowledge to support `REUSE`, `IMPROVE`, `CREATE`, and `NO_ACTION` decisions. Retrieval quality will depend on chunking, indexing and later semantic search. If the system starts with opaque vector-store rows or random chunk identities, it becomes difficult to prove what exact source content a recommendation relied on, whether access policy was preserved, or whether a later indexing change altered evidence boundaries.

The system therefore needs a canonical evidence unit before introducing semantic retrieval.

## Options considered

### 1. Store only raw documents and let each retriever chunk independently

Simple initially, but chunk identity and evidence boundaries become retriever-specific and hard to reproduce.

### 2. Store only vector/index representations

Fast for a RAG prototype, but weak for provenance, access governance and exact citation reconstruction.

### 3. Canonical governed chunks with deterministic generation

Create a first-class `KnowledgeChunk` with exact source offsets, fingerprints, access policy and strategy version, then treat lexical/vector indexes as secondary representations.

## Decision

Tropos will treat `KnowledgeChunk` as the canonical retrieval evidence unit and will establish a **deterministic, lossless chunking baseline before semantic/vector retrieval**.

A valid chunk set must preserve:

- exact source text coverage;
- stable identity for the same source state and strategy;
- source system/record/version provenance;
- source and content fingerprints;
- inherited access policy;
- chunking strategy version;
- contiguous, gap-free, overlap-free ordering.

Embeddings and search indexes, when introduced, represent chunks; they do not replace the canonical evidence model.

## Rationale

Tropos is a governed knowledge system, not merely a question-answering demo. Reproducible evidence is therefore a product requirement.

The deterministic baseline also creates a controlled starting point for later retrieval experiments. If semantic retrieval is added, the team can measure improvement without simultaneously changing the evidence model.

## Consequences

### Positive

- exact evidence can be traced back to source ranges;
- reprocessing the same source/strategy yields stable identities;
- access semantics survive chunking;
- later search technologies remain replaceable;
- retrieval/citation regressions can be investigated at chunk level;
- strategy changes are observable through `strategy_version` and changed IDs.

### Negative / trade-offs

- more metadata per chunk;
- deterministic character/structural chunking may not be semantically optimal;
- canonical chunk persistence must later handle source/version lifecycle explicitly;
- changing the chunking strategy can produce a new evidence set and require re-indexing/evaluation.

## Evidence

Implemented in:

- `domain/access.py`
- `domain/knowledge.py`
- `domain/knowledge_chunk.py`
- `application/ingestion/raw_record.py`
- `application/ports/chunking.py`
- `adapters/chunking/deterministic.py`
- corresponding domain, ingestion and chunking unit tests.

`validate_chunk_set` proves full contiguous source coverage and metadata consistency. `DeterministicKnowledgeChunker` derives stable chunk IDs from source identity, source fingerprint, strategy version, offsets and exact text fingerprint.

## Revisit when

Revisit the chunking algorithm when retrieval evaluation demonstrates a measurable failure that the current structural/character baseline cannot address.

Possible future alternatives include semantic segmentation, heading-aware parsing or content-type-specific chunkers, but any replacement must preserve the governed evidence contract and be evaluated against the existing baseline.
