# Ingestion and normalization

Tropos separates source acquisition, exact source capture, parser output, and canonical knowledge identity. A source artifact can change because of formatting or metadata without changing the knowledge it represents, while a small business-content change must create a new canonical version.

## Pipeline

```mermaid
flowchart LR
    S[(Source record)]
    --> X[KnowledgeSourceConnector]
    --> R[RawKnowledgeRecord]
    --> P[DeterministicKnowledgeParser]
    --> E[ExtractedKnowledgeText]
    --> N[DeterministicKnowledgeNormalizer]
    --> C[NormalizedKnowledge]
    --> V[Version resolver]
    --> D[KnowledgeDocument]
    --> H[DeterministicKnowledgeChunker]
    --> K[KnowledgeChunk]
    --> DB[(SQLite persistence)]
```

Connectors are optional for push-style ingestion: callers that already hold a valid `RawKnowledgeRecord` can enter directly at the raw ingestion boundary. See [Source integration](SOURCE_INTEGRATION.md) for connector responsibilities and extension rules.

Parsing v1 routes by normalized MIME content type and supports UTF-8 plain text, Markdown, HTML, and DOCX. PDF, OCR, scanned-document extraction, and multimodal parsing are not implemented yet.

## Parsing

`DeterministicKnowledgeParser` keeps canonical ingestion deterministic and source-aware.

| Source | Strategy | Output format |
| --- | --- | --- |
| Plain text | UTF-8 decode with invalid-byte rejection | Plain text |
| Markdown | Preserve source Markdown and derive title from heading when available | Markdown |
| HTML | Deterministic HTML parsing; remove executable/noise tags; preserve headings, paragraphs, and list semantics | Markdown |
| DOCX | Parse OOXML package; preserve headings, lists, table row text, and document title | Markdown |

Unsupported formats fail closed with `UnsupportedContentTypeError`. Malformed supported documents raise `KnowledgeParseError` rather than silently degrading or replacing source bytes.

HTML and DOCX are rendered into Markdown because the current normalization contract already understands explicit headings and ordered/unordered list markers. DOCX table cells are currently retained as textual rows; tables are not yet first-class canonical blocks.

No model call participates in parsing v1. A future probabilistic parser must define how its output is validated before it can affect canonical identity.

## Identity layers

| Identity | Input | Purpose | Drives canonical content version? |
| --- | --- | --- | --- |
| Source namespace + record ID | Configured source instance + source-native identity | Distinguish source records across connectors | No |
| `raw_payload_fingerprint` | Exact payload bytes | Artifact integrity and replay | No |
| `ingestion_fingerprint` | Source envelope + exact bytes | Captured-state identity and provenance | No |
| `normalized_content_fingerprint` | Canonical title + ordered structural blocks | Logical knowledge identity | Yes |
| Chunk `content_fingerprint` | Exact canonical chunk text | Evidence-span integrity | No |

The upstream `source_version` remains provenance. It does not create a Tropos content version by itself.

## Raw capture

`RawKnowledgeRecord` stores the inbound source envelope:

- source namespace, record ID, and source version;
- content type;
- exact payload bytes;
- access policy;
- capture timestamp;
- raw-payload and ingestion fingerprints.

The raw record remains immutable so parsing and canonicalization do not erase what Tropos received.

## Deterministic normalization

`canonical-text-v1` applies deterministic transformations only:

- Unicode NFC normalization;
- UTF byte-order-mark removal from extracted text;
- CRLF/CR to LF line-ending normalization;
- trailing horizontal-whitespace removal;
- repeated blank-line collapse;
- stable inline whitespace for titles, paragraphs, and list items;
- leading/trailing trim.

No model call, paraphrasing, summarization, or semantic rewriting participates in canonical identity.

## Structural extraction

The current structural vocabulary is intentionally small:

```text
StructuralBlock
├── HEADING(level 1..6)
├── PARAGRAPH
├── UNORDERED_LIST_ITEM
└── ORDERED_LIST_ITEM
```

ATX headings are recognized only when `TextFormat.MARKDOWN` is supplied. Ordered and unordered list markers are recognized for both supported format hints. Equivalent marker styles within the same list type are normalized, while ordered and unordered lists remain distinct. Plain text does not infer headings.

The normalized title and ordered block sequence are serialized as stable JSON. SHA-256 of that serialization becomes `normalized_content_fingerprint`. The same blocks render the canonical text stored in `KnowledgeDocument.content`.

This coupling means equal canonical fingerprints under the same strategy also produce equal canonical text for downstream chunking.

## Version resolution

The persisted comparison state is:

```text
CanonicalKnowledgeState
├── content_fingerprint
├── normalization_strategy_version
└── access_fingerprint
```

The resolver returns a primary content action and an independent governance-refresh signal.

| Candidate state | Primary action | Governance refresh |
| --- | --- | --- |
| First observed content | `CREATE_VERSION` | No separate refresh |
| Same canonical content and same access | `NO_CONTENT_VERSION` | No |
| Same canonical content, access changed | `REFRESH_GOVERNANCE` | Yes |
| Canonical content changed | `CREATE_VERSION` | Yes if access also changed |
| Normalization strategy changed | `REBASELINE_REQUIRED` | Yes if access also changed |

A normalization-strategy change is not treated as proof that business content changed. It requires an explicit rebaseline because a new algorithm can change canonical identity across the corpus.

## Governance changes

Content and authorization have separate lifecycles. A document can change content and access policy in the same source update.

`VersionDecision.requires_governance_refresh` preserves that second obligation even when the primary action is `CREATE_VERSION` or `REBASELINE_REQUIRED`. The SQLite persistence adapter updates governance on the currently persisted document/chunks before later content work proceeds when both dimensions change. Search indexing is not implemented yet, so cross-store index consistency remains future work.

## Durable orchestration

`IngestKnowledge` coordinates parsing, normalization, previous-state lookup, version resolution, governance refresh, chunking, and persistence without owning the implementation details of those steps.

The SQLite baseline persists:

- immutable source captures;
- ingestion-run stage/outcome/failure state;
- current canonical comparison state;
- canonical document versions;
- governed chunks.

Duplicate completed captures are idempotent, and expected-state checks surface concurrent canonical updates rather than silently overwriting them.

## Chunk identity

Chunk identity derives from canonical evidence rather than noisy upstream state:

```text
knowledge_id
+ normalized_content_fingerprint
+ normalization_strategy_version
+ chunking_strategy_version
+ start_offset
+ end_offset
+ exact_chunk_text_fingerprint
```

`source_version` and `ingestion_fingerprint` remain lineage fields. Formatting-only source churn therefore does not create unrelated chunk IDs when canonical content is unchanged.

## Guarantees

The implemented ingestion foundation guarantees that:

1. Source acquisition can be replaced independently of downstream canonical processing.
2. Exact source evidence remains separately identifiable.
3. Supported source formats are parsed deterministically before normalization.
4. Unsupported or malformed sources fail explicitly.
5. Canonical identity is deterministic for a given normalization strategy.
6. Presentation-only changes covered by the normalizer do not create content versions.
7. Meaning-bearing text or structural changes change canonical identity.
8. Access changes remain independently observable from content changes.
9. Normalizer changes require explicit rebaselining.
10. Canonical text and canonical fingerprint derive from the same structural representation.
11. Chunk identity derives from canonical content identity while raw/source state remains provenance.
12. Canonical versions and chunks are stored durably behind application persistence ports.

## Known limits

External enterprise connectors, connector discovery/sync, PDF, OCR, scanned documents, images, and multimodal extraction are not implemented. DOCX tables are retained as text rather than canonical table objects.

`canonical-text-v1` does not yet provide first-class semantics for tables, code blocks, embedded objects, or images, and it does not attempt semantic equivalence between genuinely different wording.

Those cases require connector/parser/canonicalization work and evaluation before they can participate safely in identity decisions.

## Implementation

- `apps/api/src/tropos/core/application/ports/sources.py`
- `apps/api/src/tropos/core/application/ingestion/ingest_from_source.py`
- `apps/api/src/tropos/core/application/ingestion/ingest_knowledge.py`
- `apps/api/src/tropos/core/application/ingestion/raw_record.py`
- `apps/api/src/tropos/core/application/ingestion/parsing.py`
- `apps/api/src/tropos/core/adapters/sources/local_file.py`
- `apps/api/src/tropos/core/adapters/parsing/deterministic.py`
- `apps/api/src/tropos/core/application/ingestion/normalization.py`
- `apps/api/src/tropos/core/application/ingestion/versioning.py`
- `apps/api/src/tropos/core/adapters/normalization/deterministic.py`
- `apps/api/src/tropos/core/domain/knowledge.py`
- `apps/api/src/tropos/core/domain/knowledge_chunk.py`
- `apps/api/src/tropos/core/adapters/chunking/deterministic.py`
- `apps/api/src/tropos/core/adapters/persistence/sqlite.py`

Related decisions:

- [ADR-004: Deterministic normalization and content versioning](../decisions/ADR-004-deterministic-normalization-and-content-versioning.md)
- [ADR-005: Independent governance refresh signal](../decisions/ADR-005-independent-governance-refresh-signal.md)
- [ADR-006: Deterministic format-aware parsing](../decisions/ADR-006-deterministic-format-aware-parsing.md)
- [ADR-007: Synchronous ingestion orchestration and SQLite persistence](../decisions/ADR-007-synchronous-ingestion-orchestration-and-sqlite-persistence.md)
- [ADR-008: Separate source connectors from format parsing](../decisions/ADR-008-source-connectors-separate-from-format-parsing.md)
