# Ingestion and normalization

Tropos separates exact source capture from canonical knowledge identity. A source artifact can change because of formatting or metadata without changing the knowledge it represents, while a small business-content change must create a new canonical version.

## Pipeline

```mermaid
flowchart LR
    S[(Source record)]
    --> R[RawKnowledgeRecord]
    --> E[ExtractedKnowledgeText]
    --> N[DeterministicKnowledgeNormalizer]
    --> C[NormalizedKnowledge]
    --> V[Version resolver]
    --> D[KnowledgeDocument]
    --> H[DeterministicKnowledgeChunker]
    --> K[KnowledgeChunk]
```

Source-format parsing sits before `ExtractedKnowledgeText`. Tropos currently accepts extracted plain text or Markdown; rich PDF, DOCX, HTML, and connector-specific parsers are planned.

## Identity layers

| Identity | Input | Purpose | Drives canonical content version? |
| --- | --- | --- | --- |
| `raw_payload_fingerprint` | Exact payload bytes | Artifact integrity and replay | No |
| `ingestion_fingerprint` | Source envelope + exact bytes | Captured-state identity and provenance | No |
| `normalized_content_fingerprint` | Canonical title + ordered structural blocks | Logical knowledge identity | Yes |
| Chunk `content_fingerprint` | Exact canonical chunk text | Evidence-span integrity | No |

The upstream `source_version` remains provenance. It does not create a Tropos content version by itself.

## Raw capture

`RawKnowledgeRecord` stores the inbound source envelope:

- source system, record ID, and source version;
- content type;
- exact payload bytes;
- access policy;
- capture timestamp;
- raw-payload and ingestion fingerprints.

The raw record remains immutable so later canonicalization does not erase what Tropos received.

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

This coupling is important: equal canonical fingerprints under the same strategy also produce equal canonical text for downstream chunking.

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

`VersionDecision.requires_governance_refresh` preserves that second obligation even when the primary action is `CREATE_VERSION` or `REBASELINE_REQUIRED`. Downstream persistence and indexing must apply new retrieval authorization without waiting for unrelated content processing.

The atomic persistence/indexing behavior for that future workflow is not implemented yet.

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

1. Exact source evidence remains separately identifiable.
2. Canonical identity is deterministic for a given normalization strategy.
3. Presentation-only changes covered by the normalizer do not create content versions.
4. Meaning-bearing text or structural changes change canonical identity.
5. Access changes remain independently observable from content changes.
6. Normalizer changes require explicit rebaselining.
7. Canonical text and canonical fingerprint derive from the same structural representation.
8. Chunk identity derives from canonical content identity while raw/source state remains provenance.

## Known limits

`canonical-text-v1` does not yet provide format-specific semantics for tables, code blocks, embedded objects, or rich document structures. It also does not attempt semantic equivalence between genuinely different wording.

Those cases require additional parser/canonicalization work and evaluation before they can participate safely in identity decisions.

## Implementation

- `apps/api/src/tropos/core/application/ingestion/raw_record.py`
- `apps/api/src/tropos/core/application/ingestion/normalization.py`
- `apps/api/src/tropos/core/application/ingestion/versioning.py`
- `apps/api/src/tropos/core/application/ports/normalization.py`
- `apps/api/src/tropos/core/adapters/normalization/deterministic.py`
- `apps/api/src/tropos/core/domain/knowledge.py`
- `apps/api/src/tropos/core/domain/knowledge_chunk.py`
- `apps/api/src/tropos/core/adapters/chunking/deterministic.py`

Related decisions:

- [ADR-004: Deterministic normalization and content versioning](../decisions/ADR-004-deterministic-normalization-and-content-versioning.md)
- [ADR-005: Independent governance refresh signal](../decisions/ADR-005-independent-governance-refresh-signal.md)
