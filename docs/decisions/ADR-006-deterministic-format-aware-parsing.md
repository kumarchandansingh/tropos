# ADR-006: Deterministic format-aware parsing

**Status:** Accepted  
**Date:** 2026-09-26

## Context

Tropos needs a source-format parsing stage between immutable raw capture and deterministic normalization. The parser must preserve useful document structure without making canonical knowledge identity depend on probabilistic model output.

The initial corpus includes text-native formats whose structure can be recovered deterministically. PDF, scanned documents, and visually rich documents require different extraction techniques and should not force a probabilistic dependency into every ingestion path.

## Options considered

1. Send every source through an LLM or multimodal document parser.
2. Use one generic text extractor for every format.
3. Route by content type and use deterministic format-aware parsers first, adding specialized fallbacks only where needed.

## Decision

Tropos will use deterministic, format-aware parsing as the default canonical ingestion path.

Parsing v1 supports:

- UTF-8 plain text;
- Markdown;
- HTML;
- DOCX.

HTML and DOCX parsers preserve headings and list semantics by rendering the extracted structure as Markdown for the existing `ExtractedKnowledgeText` contract. Unsupported formats fail closed.

PDF parsing, OCR, document-AI, and multimodal/LLM parsing remain separate future adapters. If probabilistic parsing is introduced, its output must be validated and its relationship to canonical identity must be explicitly designed rather than silently replacing deterministic extraction.

## Consequences

### Positive

- identical source bytes produce reproducible parser output;
- canonical fingerprints do not depend on model nondeterminism;
- format-specific structure is preserved where the source exposes it;
- parser dependencies can evolve independently of normalization and chunking;
- unsupported or malformed sources are explicit failures rather than silent lossy ingestion.

### Negative / trade-offs

- parsing v1 does not support PDF or OCR;
- DOCX tables are preserved as textual rows rather than first-class table blocks;
- richer source semantics require expansion of the canonical structural vocabulary before they can participate in version identity.

## Evidence

- `apps/api/src/tropos/core/application/ingestion/parsing.py`
- `apps/api/src/tropos/core/adapters/parsing/deterministic.py`
- `apps/api/tests/unit/core/adapters/parsing/test_deterministic_parser.py`

## Revisit when

Revisit this decision when retrieval quality requires richer table/code/image structure, when PDF/scanned documents become a required ingestion source, or when deterministic parsers cannot recover sufficient structure from a material share of the corpus.
