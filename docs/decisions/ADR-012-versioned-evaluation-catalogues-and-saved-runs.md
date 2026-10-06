# ADR-012: versioned evaluation catalogues and saved runs

Status: accepted for the local synthetic evaluation foundation.

## Context

A metric printed by a test does not tell a reviewer which cases were planned, whether execution failed, or which evidence was returned. Editing labels after a run can make its result impossible to explain. We need this boundary before adding a model or dashboard.

## Decision

Add an explicit schema-validated catalogue and immutable dataset snapshots. Keep expected behavior separate from durable case executions, returned evidence and assertions. Use a dedicated SQLite store with relational run/case identities and append-only result details. Reuse the retrieval port. Execute each synthetic scenario in an isolated fixture database through actual ingestion and BM25. Expose CLI JSON/Markdown reports before building the visualizer.

Store expected relevance separately from invariant outcomes. A relevance gain cannot erase an unauthorized or outdated result. Error, not-run and interrupted states are observable and cannot be reported as passes. Invalid evidence is withheld from report hits and quality averages.

## Alternatives and costs

Console output alone is simpler but not a durable review record. A dashboard-first implementation risks inventing statuses without an execution contract. A hosted evaluation platform would add identity, data-sharing and operations requirements before the local baseline is established.

SQLite suits single-process local use. Per-case ingestion is slower but prevents state leakage between lifecycle scenarios. The V2 catalogue remains a small synthetic development seed. We do not claim semantic improvement, held-out validation or production readiness.

## Revisit

Introduce resumable workers and stronger schema migrations when runs become long or concurrent. Add hosted report authorization before storing real private evidence. Adopt stable evidence anchors and chunk-level labels when multi-chunk documents make knowledge-level judgments insufficient. Add tamper-evident storage only if audit requirements demand it.
