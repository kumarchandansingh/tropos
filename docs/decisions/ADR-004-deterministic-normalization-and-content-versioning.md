# ADR-004: Separate source identity from deterministic canonical content versioning

**Status:** Accepted  
**Date:** 2026-09-21

## Context

Tropos captures knowledge from upstream systems that may change bytes, formatting, metadata or source-version numbers without changing the knowledge a user should retrieve. If raw/source identity directly drives canonical versions and chunk IDs, presentation-only changes can trigger duplicate versions, unnecessary re-chunking/re-indexing and later unnecessary embedding cost.

The opposite failure is also unacceptable: a small but meaningful change such as `90 days` to `60 days` must be observable as a new canonical content state.

Tropos also needs access-policy changes to take effect even when content does not change, and it needs a safe response when the normalization algorithm itself changes.

## Options considered

### 1. Trust the upstream source version

Easy to implement, but source systems have different version semantics. Some increment on formatting/metadata changes; others may not provide a reliable version at all.

### 2. Hash raw payload bytes and use that as the knowledge version

Deterministic and auditable, but over-sensitive. Line endings, whitespace or format-only edits become fake knowledge versions.

### 3. Use an LLM to normalize or summarize before fingerprinting

Potentially semantically powerful, but unsuitable for foundational identity: model/provider/prompt changes and nondeterminism can alter identity without a source change, and paraphrasing weakens evidence fidelity.

### 4. Preserve raw identity and add deterministic canonical normalization

Keep exact-source identity for audit/replay, then produce a versioned deterministic canonical representation for content comparison. Model access/governance independently.

## Decision

Tropos adopts option 4.

The ingestion path has distinct identity layers:

1. **Raw payload fingerprint** — SHA-256 of exact captured bytes.
2. **Ingestion fingerprint** — SHA-256 of canonical source-envelope metadata plus exact bytes.
3. **Normalized content fingerprint** — SHA-256 of deterministic canonical title + ordered structural blocks.
4. **Chunk content fingerprint** — SHA-256 of exact canonical chunk text.

Canonical content-version decisions use the **normalized content fingerprint**, not raw bytes or the source-system version alone.

Normalization is explicitly versioned. `canonical-text-v1` performs deterministic text cleanup plus conservative structural extraction. No LLM rewriting participates in identity/versioning.

When the normalization strategy version changes, Tropos returns `REBASELINE_REQUIRED` rather than assuming a business-content change.

Access-policy state is fingerprinted independently. When content is unchanged but access changes, the version resolver returns `REFRESH_GOVERNANCE` rather than creating a content version.

Canonical `KnowledgeDocument.content` is rendered from the same structural blocks used for the canonical fingerprint. This prevents equal canonical fingerprints from later producing different chunk boundaries.

Chunk identity is based on normalized content identity + normalization strategy + chunking strategy + exact span/text identity. Source version and ingestion fingerprint remain lineage, not chunk-identity noise.

## Rationale

Tropos is a governed evidence system. It needs both forensic fidelity and stable logical identity. Those are different requirements and should not be collapsed into one hash.

The chosen design supports:

- auditability of the exact received artifact;
- idempotent reprocessing;
- stable identity across presentation-only changes;
- explicit content-version creation for meaningful changes;
- independent security/governance refresh;
- controlled migrations when normalization behavior changes;
- reproducible chunk identity over canonical evidence.

## Consequences

### Positive

- format/source-version churn no longer implies knowledge-version churn;
- content changes are detected from deterministic canonical evidence;
- ACL updates can invalidate/refresh retrieval state independently;
- normalizer changes become explicit migration events;
- chunk IDs remain stable across irrelevant upstream changes;
- future persistence/indexing can store both raw provenance and canonical identity.

### Negative / trade-offs

- the model now carries several fingerprints with deliberately different meanings;
- canonicalization rules are product-critical and require regression tests;
- rich formats such as tables, code blocks, DOCX and PDF need additional deterministic extractors/parsers;
- `canonical-text-v1` cannot decide semantic equivalence between genuinely different wording;
- strategy changes require a rebaseline process rather than transparent replacement.

## Evidence

Implementation:

- `core/application/ingestion/raw_record.py`
- `core/application/ingestion/normalization.py`
- `core/application/ingestion/versioning.py`
- `core/application/ports/normalization.py`
- `core/adapters/normalization/deterministic.py`
- `core/domain/knowledge.py`
- `core/domain/knowledge_chunk.py`
- `core/adapters/chunking/deterministic.py`

Tests demonstrate:

- line-ending/whitespace/list-marker formatting equivalence;
- Unicode canonical equivalence;
- meaningful text change detection;
- heading-level structural change detection;
- deterministic replay;
- access-only governance refresh;
- source-version churn without content-version churn;
- explicit rebaseline on normalizer-version change;
- canonical-content-based chunk identity.

Living design: `docs/architecture/INGESTION_NORMALIZATION.md`.

## Revisit when

Revisit the canonical model when one of these is demonstrated by real fixtures/evaluations:

- table/code/list semantics are lost by the current structural vocabulary;
- source formats require format-specific parsers to preserve meaning;
- multilingual Unicode/text rules need expansion;
- deterministic normalization cannot meet a measured dedup/versioning requirement;
- semantic equivalence is required strongly enough to justify an AI-assisted secondary signal.

Any future AI-assisted equivalence detector should remain a separate, evaluated decision aid unless a new ADR explicitly promotes it into canonical identity.
