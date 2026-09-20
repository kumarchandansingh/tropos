# Knowledge Model

## Purpose

Tropos treats knowledge as governed evidence, not just text. A knowledge unit must retain identity, exact source lineage, access policy, and processing lineage so later retrieval and recommendations can be traced back to source material.

## Theory foundation

This design combines four ideas:

- **Information architecture** — knowledge objects have explicit identities and relationships.
- **Data provenance / lineage** — transformations retain where data came from and how it changed.
- **Content-addressable verification** — fingerprints make exact content changes detectable.
- **Policy inheritance** — access constraints follow the knowledge they govern.

## Core model

```mermaid
classDiagram
    class KnowledgeDocument {
      knowledge_id
      source_system
      source_record_id
      source_version
      title
      content
      source_fingerprint
      access_policy
    }

    class KnowledgeChunk {
      chunk_id
      knowledge_id
      sequence_number
      text
      start_offset
      end_offset
      content_fingerprint
      source_fingerprint
      strategy_version
      access_policy
    }

    class AccessPolicy {
      indexability
      visibility / policy semantics
    }

    KnowledgeDocument "1" --> "many" KnowledgeChunk : deterministically chunked into
    KnowledgeDocument --> AccessPolicy
    KnowledgeChunk --> AccessPolicy : inherits
```

## Why a chunk is more than text

```mermaid
flowchart TB
    KC[KnowledgeChunk]
    KC --> I[Identity<br/>chunk ID / knowledge ID / sequence]
    KC --> SL[Source lineage<br/>system / record / version / source fingerprint]
    KC --> E[Exact evidence<br/>text / offsets / content fingerprint]
    KC --> G[Governance<br/>access policy]
    KC --> PL[Processing lineage<br/>chunking strategy version]
```

This structure supports a key Tropos invariant: **retrieved evidence must remain explainable as an exact occurrence within a governed source version**.

## Deterministic chunking invariants

Tropos currently validates that a generated chunk set:

- is non-empty;
- has contiguous sequence numbers;
- contains unique chunk IDs;
- has no gaps or overlaps;
- exactly matches the corresponding source ranges;
- inherits source metadata and access policy;
- uses one chunking strategy version across the set;
- covers the complete document.

```mermaid
flowchart LR
    S[Source document] --> C1[Chunk 0]
    C1 --> C2[Chunk 1]
    C2 --> C3[Chunk n]
    S -. exact contiguous coverage .-> C1
    S -. exact contiguous coverage .-> C2
    S -. exact contiguous coverage .-> C3
```

## Why offsets + fingerprints both exist

| Mechanism | What it proves |
| --- | --- |
| `start_offset` / `end_offset` | Where the evidence occurs in the source text |
| `content_fingerprint` | The exact chunk text has not silently changed |
| `source_fingerprint` | The chunk is tied to a specific source content state |
| `source_version` | The upstream system's version identity |
| `strategy_version` | Which chunking behavior produced the chunk |

No one field is sufficient by itself. Together they provide stronger traceability.

## Best-practice mapping

| Best practice | Tropos implementation |
| --- | --- |
| Preserve provenance | Source system, record, version, fingerprint |
| Make transformations reproducible | Deterministic chunker + strategy version |
| Keep evidence locatable | Character offsets |
| Prevent accidental evidence drift | Content fingerprint validation |
| Respect information governance | Access policy inherited by chunks |
| Separate domain semantics from retrieval technology | Chunk is a domain object, not a vector-database row |

## Future extension

Persistence and retrieval should enrich this model rather than replace it.

```mermaid
flowchart LR
    Doc[KnowledgeDocument] --> Chunk[KnowledgeChunk]
    Chunk --> Persist[(Persistent store)]
    Chunk --> Lexical[FTS index]
    Chunk -. later .-> Embed[Embedding]
    Lexical --> Result[RetrievalResult]
    Embed -. later .-> Result
    Result --> Evidence[Evidence-backed recommendation]
```

A future embedding is therefore an **indexing representation of a chunk**, not the source of truth for the chunk itself.

## Failure modes to avoid

- storing only vectors and losing exact source evidence;
- generating chunk IDs randomly so re-indexing produces unrelated identities;
- allowing ACLs to disappear between source and index;
- using chunk text without source version/fingerprint;
- changing chunking behavior without versioning the strategy;
- conflating source documents, chunks, retrieval results, and generated answers into one model.
