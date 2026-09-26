# Architecture overview

Tropos is a modular monolith with Ports-and-Adapters boundaries. The architecture separates reusable governed-knowledge mechanics from capability-specific policy and keeps infrastructure dependencies outside the domain model.

## Module boundaries

```mermaid
flowchart TB
    subgraph Core[Tropos Core]
      Source[Source connector]
      Raw[Raw capture]
      Norm[Normalization and versioning]
      Doc[KnowledgeDocument]
      Chunk[KnowledgeChunk]
      Store[(Persistence)]
      Source --> Raw --> Norm --> Doc --> Chunk --> Store
    end

    subgraph Resolve[Tropos Resolve]
      Case[ResolvedCase]
      Closure[Closure evidence]
      Retrieval[Retrieval and coverage contracts]
      Action[REUSE / IMPROVE / CREATE / NO_ACTION]
      Case --> Closure --> Retrieval --> Action
    end

    Chunk -. governed evidence .-> Retrieval
```

`tropos.core` owns reusable source integration, evidence identity, access, parsing, normalization, versioning, chunking, and persistence contracts/adapters. `tropos.capabilities.resolve` owns support-case workflow and knowledge-action policy.

## Dependency direction

```mermaid
flowchart TB
    Presentation[Future API / CLI / UI]
    CapApp[Capability application]
    CapDomain[Capability domain]
    CoreApp[Core application and ports]
    CoreDomain[Core domain]
    Adapters[Adapters]
    External[(Sources / stores / parsers / search / models)]

    Presentation --> CapApp
    Presentation --> CoreApp
    CapApp --> CapDomain
    CapApp --> CoreDomain
    CoreApp --> CoreDomain
    Adapters --> CoreApp
    Adapters --> CoreDomain
    Adapters --> External
```

Domain and application policy do not depend on database sessions, search engines, model SDKs, web frameworks, or source-system clients. Those dependencies belong in adapters or outer composition layers.

## Current implementation

| Boundary | Responsibility | Status |
| --- | --- | --- |
| Core domain | Access policy, canonical knowledge documents, governed chunks | Implemented |
| Core application | Source-capture contracts, ingestion orchestration, normalization contracts, version resolution | Implemented |
| Source adapters | Local-file source capture | Implemented |
| Parsing adapters | Deterministic plain-text, Markdown, HTML, and DOCX parsing | Implemented |
| Processing adapters | Deterministic normalizer and deterministic chunker | Implemented |
| Persistence | SQLite source/run/canonical document/version/chunk storage | Implemented |
| Resolve domain | Resolved-case and knowledge-action policy | Implemented |
| Resolve application | Closure-evaluation orchestration and retrieval/coverage/store ports | Implemented contracts and orchestration |
| External connectors | SharePoint, Gmail, Jira, Confluence, and similar sources | Planned |
| Retrieval | Lexical search and retrieval adapter | Planned |
| Coverage | Concrete coverage evaluator | Planned |
| Model assistance | Embeddings, hybrid retrieval, LLM reasoning/drafting | Deferred until baseline evaluation |
| Presentation/deployment | API, UI, hosted environments | Planned |

## Source and ingestion boundary

```mermaid
flowchart LR
    Source[(Source system)]
    --> Connector[KnowledgeSourceConnector]
    --> Capture[SourceCapture]
    --> Raw[RawKnowledgeRecord]
    --> Parse[KnowledgeParser]
    --> Extract[ExtractedKnowledgeText]
    --> Norm[Deterministic normalization]
    --> Version[Canonical version resolution]
    --> Doc[KnowledgeDocument]
    --> Chunk[KnowledgeChunk]
    --> Store[(SQLite)]
```

Source acquisition and content-format parsing are intentionally separate. A SharePoint connector and a Gmail connector may both produce HTML; they should reuse the same HTML parser rather than duplicating parsing behavior. Conversely, one source system may expose several formats without changing the ingestion orchestrator.

This pipeline keeps these concerns separate:

- source-system acquisition and native identity;
- exact source evidence;
- format interpretation;
- canonical content identity;
- access/governance state;
- normalization strategy;
- chunking strategy;
- durable persistence.

See [Source integration](SOURCE_INTEGRATION.md) for connector boundaries and [Ingestion and normalization](INGESTION_NORMALIZATION.md) for canonicalization/version rules.

## Responsibility table

| Layer | Owns | Excludes |
| --- | --- | --- |
| Core domain | Evidence and access invariants | Vendor SDKs, persistence, HTTP clients |
| Core application | Core use cases and replaceable contracts | Vendor-specific behavior |
| Core adapters | Source integrations, deterministic algorithms, persistence implementations | Capability-specific policy |
| Capability domain | Capability vocabulary and business rules | Infrastructure |
| Capability application | Capability orchestration | Vendor-specific infrastructure |
| Presentation/bootstrap | Request translation and dependency wiring | Domain decisions |

Presentation/bootstrap are target boundaries; no production API or runtime composition layer exists yet.

## Architectural guarantees

The implemented foundation maintains these guarantees:

1. New source connectors can enter through a stable capture contract without adding source-specific branches to `IngestKnowledge`.
2. Source acquisition is separate from content-format parsing.
3. Raw source identity is separate from canonical content identity.
4. Normalization and version resolution are deterministic and strategy-versioned.
5. Presentation-only changes do not create canonical content versions.
6. Access changes remain independently observable from content changes.
7. Canonical fingerprints and canonical text derive from the same normalized structure.
8. Retrieval evidence remains traceable to canonical content and captured source state.
9. Capability policy remains isolated from reusable core mechanics.

Changes to these guarantees require an architecture decision record.

## Related documents

- [Codebase map](CODEBASE_MAP.md)
- [Source integration](SOURCE_INTEGRATION.md)
- [Ingestion and normalization](INGESTION_NORMALIZATION.md)
- [Knowledge model](KNOWLEDGE_MODEL.md)
- [RAG architecture](RAG_ARCHITECTURE.md)
- [Architecture decisions](../decisions/README.md)
