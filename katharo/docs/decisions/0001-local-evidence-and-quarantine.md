# ADR 0001: deterministic evidence with explicit quarantine

Status: Accepted for initial local release.

## Context

Repeated filenames can contain different data; identical extracted text can conceal valuable formatting or job positioning. Immediate deletion makes recovery harder. An enterprise service would add unnecessary deployment complexity for an initial single-PC workflow.

## Decision

Use Python modules and a local browser interface. Stream SHA-256 for raw equality and byte-verify before executing. Keep parsing separate from raw matching; document similarities remain review-only. Persist plans in SQLite and original-path manifests. Move approved exact extras into a user-selected quarantine outside the scan root.

Use standard library server and test tooling for the initial release, with pypdf for PDF extraction. This differs from Tropos's pytest/uv tooling while retaining its deterministic boundaries, separate documentation purposes, and behavioral release checks.

## Consequences

The app works without cloud inference or uploading files. Same-drive moves are fast but do not free space. Cross-drive actions need verified copies. Restoration is possible only while quarantine contents remain; occupied original paths block restoration. SQLite is sufficient for a single local service, not multi-machine concurrent writers.

## Alternatives

Recycle Bin: familiar but programmatic restore and manifests are less explicit.
Copy-only review folder: leaves all original storage occupied and duplicates it.
Semantic auto-cleanup: deferred; similarity cannot establish dispensability.
