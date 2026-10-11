# Sources and Ingestion Experience

Status: Active product and architecture contract  
Scope: First operational Tropos vertical slice

## User outcome

An AI/platform administrator can add a supported file to Tropos and understand whether it became new governed knowledge, changed only access metadata, produced no canonical content change, or requires intervention.

The command-line interface is the first executable surface. The object model and states are intentionally designed for the later **Sources & Ingestion** product experience rather than as a throwaway CLI workflow.

## Reference patterns

Tropos uses mature products as interaction references while retaining its own governed-knowledge model.

| Reference | Pattern adopted | Tropos interpretation |
|---|---|---|
| Glean Admin | Sources/connectors are durable managed objects and access is part of source administration | Source identity and access lineage remain separate from an ingestion execution |
| Unstructured Platform | Source/workflow/job are distinct concepts | A durable source capture is not the same thing as an ingestion run |
| Dify Knowledge | Documents expose indexing/processing/error state | Knowledge availability and ingestion outcome must be inspectable instead of hidden behind upload success |

References:
- https://docs.glean.com/administration/about
- https://docs.unstructured.io/platform-api/api/overview
- https://docs.dify.ai/

## Personas and user stories

Primary persona: AI / Platform Admin.

- As an admin, I want to ingest a local TXT, Markdown, HTML, or DOCX file so that it becomes governed Tropos knowledge.
- As an admin, I want a repeated upload to tell me whether canonical knowledge actually changed.
- As an admin, I want access-only changes to remain distinct from content-version changes.
- As an admin, I want a failed or unsupported ingestion to return an actionable state rather than a silent partial success.
- As an operator, I want a successful ingest to be immediately available to the lexical retrieval path.

## Information architecture

The target product navigation remains:

```text
Sources & Ingestion
├── Sources
├── Add Source / Upload
├── Ingestion Runs
├── Documents / Knowledge Records
└── Failures
```

This PR implements the operational workflow behind those surfaces; it does not add a visual frontend.

## UX flow

```text
Choose file
   ↓
Resolve source identity + access
   ↓
Capture immutable source bytes
   ↓
Parse
   ↓
Normalize
   ↓
Compare with canonical state
   ↓
┌───────────────────────────────┐
│ VERSION_CREATED               │ → Available
│ NO_CHANGE                     │ → Available; no content change
│ GOVERNANCE_REFRESHED          │ → Available; access updated
│ REBASELINE_REQUIRED           │ → Action required
└───────────────────────────────┘
   ↓
Chunk current canonical version
   ↓
Persist
   ↓
Ensure lexical FTS projection exists
```

Run presentation must also distinguish queued/processing from completed outcomes when execution becomes asynchronous. Failure states remain distinct: unsupported artifact, source not found, parse failure, persistence/runtime failure, and rebaseline-required.

## UI state contract

A later UI should map the existing runtime outcomes without inventing new semantics:

| Runtime outcome | Product-language state |
|---|---|
| VERSION_CREATED | Available — new version created |
| NO_CHANGE | Available — no content change |
| GOVERNANCE_REFRESHED | Available — access updated |
| REBASELINE_REQUIRED | Action required — rebaseline |
| Failed run | Failed — inspect stage/error |

A formatting-only source change must not appear to users as a new knowledge version.

## Object-model audit

| Existing object | Product concept | Decision |
|---|---|---|
| `LocalFileSourceConnector` / `KnowledgeSourceConnector` | Source/connector boundary | Reuse |
| `SourceCapture` / `RawKnowledgeRecord` | Immutable captured source evidence | Reuse |
| `IngestionResult` + persisted `ingestion_runs` | Ingestion run/job and outcome | Reuse; do not create a duplicate `IngestionJob` abstraction yet |
| `CanonicalKnowledgeState` | Current knowledge state | Reuse |
| `KnowledgeDocument` | Canonical knowledge version | Reuse |
| `KnowledgeChunk` | Searchable derived evidence unit | Reuse |
| `SQLiteFtsKnowledgeRetriever` | Lexical derived projection | Reuse and initialize after ingestion |

Future connector configuration may require a durable `SourceConnection` concept. It is intentionally not invented in this PR because local-file ingestion already has a stable connector boundary and no persistent connection configuration is required yet.

## Functional architecture

```text
Local file
  → LocalFileSourceConnector
  → RawKnowledgeRecord
  → DeterministicKnowledgeParser
  → DeterministicKnowledgeNormalizer
  → version decision
  → KnowledgeDocument
  → DeterministicKnowledgeChunker
  → SQLiteIngestionStore
  → SQLite FTS5 projection
```

Canonical records remain authoritative. FTS is a rebuildable projection. Dense embeddings remain derived state and are not fabricated by this command when no embedding provider is configured.

## Security and governance

- Local paths are constrained below the connector root.
- Access policy is attached at capture time and inherited by chunks.
- Restricted knowledge is only retrievable by matching groups.
- No caller-supplied access group is converted into a trusted runtime identity here; verified-principal runtime resolution remains a later vertical-slice boundary.
- Source bytes are preserved as immutable capture evidence.
- The command does not weaken current-version or lifecycle filtering in retrieval.

## CLI

```text
tropos ingest runbook.docx
tropos ingest runbook.docx --tenant acme
tropos ingest runbook.docx --tenant acme --group support-l3
```

The default local database is `.tropos/tropos.db`.

## Acceptance evidence

The PR must prove:

1. supported local files execute the existing parse → normalize → version → chunk → persist path;
2. successful content is immediately retrievable through SQLite FTS5;
3. formatting-only changes produce `NO_CHANGE`;
4. restricted knowledge cannot be retrieved by a non-matching group;
5. existing lifecycle/versioning rules remain authoritative;
6. unsupported/failing inputs produce explicit errors;
7. no new parallel ingestion or knowledge abstractions are introduced.
