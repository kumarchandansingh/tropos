# ADR-008: Separate source connectors from format parsing

**Status:** Accepted  
**Date:** 2026-09-26

## Context

Tropos needs to ingest knowledge from heterogeneous systems such as local files, SharePoint, Gmail, Jira, and Confluence. Those systems differ in authentication, record lookup, source-native versioning, ACL models, and APIs, while many of them deliver the same underlying content formats such as HTML, Markdown, DOCX, or PDF.

Embedding source-specific logic in `IngestKnowledge` would make the orchestrator grow a branch for every integration. Letting parsers fetch external systems would mix transport/authentication concerns with content interpretation and make parser behavior depend on vendor SDKs.

## Options considered

1. Add source-specific branches directly to the ingestion orchestrator.
2. Let each format parser also fetch records from external systems.
3. Introduce a source-connector port that emits a common capture envelope, then feed that envelope into the existing ingestion workflow.

## Decision

Tropos will separate source acquisition from format parsing.

A `KnowledgeSourceConnector` captures one source-native record and returns `SourceCapture`. The capture carries an immutable `RawKnowledgeRecord` plus optional source URI and source-update metadata. `IngestFromSource` bridges that capture into the existing `IngestKnowledge` orchestrator.

`RawKnowledgeRecord.source_system` is treated as a stable configured source-instance namespace rather than only a generic vendor/product name. Native record identifiers are interpreted within that namespace so independent source instances can safely contain overlapping record IDs.

The first adapter is `LocalFileSourceConnector`. It proves the boundary without introducing an external SDK and maps supported local files into the same raw ingestion contract already used by parser, normalization, versioning, chunking, and persistence.

External connector discovery, bulk synchronization, cursors, credentials, webhook ingestion, and deletion/tombstone semantics remain outside this slice.

## Consequences

### Positive

- adding a source does not require source-specific branches in `IngestKnowledge`;
- connector SDKs and authentication remain outside core domain/application policy;
- the same format parser can be reused across many source systems;
- push-style API ingestion and pull-style connector ingestion can converge on the same raw boundary;
- source identity becomes explicit at the configured-source-instance level;
- connector-specific version tokens remain provenance and do not directly create canonical content versions.

### Negative / trade-offs

- composition code must choose/configure the correct connector;
- source namespace conventions must be stable because they participate in ingestion identity;
- local-file access policy is configured rather than derived from a native ACL;
- external source lifecycle concerns such as deletion and incremental sync are not yet modeled.

## Evidence

- `apps/api/src/tropos/core/application/ports/sources.py`
- `apps/api/src/tropos/core/application/ingestion/ingest_from_source.py`
- `apps/api/src/tropos/core/adapters/sources/local_file.py`
- `apps/api/tests/unit/core/adapters/sources/test_local_file_source.py`
- `docs/architecture/SOURCE_INTEGRATION.md`

## Revisit when

Revisit this decision if a material source cannot be represented as record-oriented captures, if cross-record transactions are required, if connector synchronization becomes asynchronous and durable, or if source-native identity requires additional first-class fields beyond the current namespace-plus-record model.
