# ADR-005: Treat governance refresh as an independent ingestion signal

**Status:** Accepted  
**Date:** 2026-09-21

## Context

ADR-004 separated canonical content identity from access-policy identity. The first implementation returned one primary `VersionAction`, with `REFRESH_GOVERNANCE` used when content stayed unchanged and access changed.

A failure-oriented review exposed an important concurrent-change case: access can change at the same time as content or normalization strategy.

For example, an article may both change from `90 days` to `60 days` **and** become restricted to a smaller group. Creating a new content version does not by itself guarantee that the currently searchable version stops using the old access policy while review, persistence or indexing work is still in progress. The same risk exists while a normalization-strategy rebaseline is pending.

Security/governance therefore cannot be hidden behind a mutually exclusive content/version action.

## Options considered

### 1. Keep one mutually exclusive action

Simple, but `CREATE_VERSION` or `REBASELINE_REQUIRED` can mask a simultaneous access change. Downstream orchestration could delay a security update until content processing finishes.

### 2. Give access changes precedence over content changes

Safer than option 1 for security, but then the content/rebaseline work becomes hidden and requires another comparison pass. The resolver would still be modelling two independent dimensions as one choice.

### 3. Keep a primary version action and emit governance refresh independently

Preserve the existing content/version vocabulary while adding an explicit `requires_governance_refresh` signal. An access change is therefore observable whether the primary action is `REFRESH_GOVERNANCE`, `CREATE_VERSION`, or `REBASELINE_REQUIRED`.

## Decision

Tropos adopts option 3.

`VersionDecision` now contains:

```text
VersionDecision
├── action
├── reason
└── requires_governance_refresh
```

The resolver computes access change independently before selecting the primary content/version action.

The resulting behavior is:

| Content / strategy state | Access state | Primary action | Governance refresh? |
| --- | --- | --- | --- |
| first seen | initial policy | `CREATE_VERSION` | No separate refresh; the new document carries the policy |
| same content | unchanged | `NO_CONTENT_VERSION` | No |
| same content | changed | `REFRESH_GOVERNANCE` | **Yes** |
| content changed | unchanged | `CREATE_VERSION` | No |
| content changed | changed | `CREATE_VERSION` | **Yes** |
| normalizer changed | unchanged | `REBASELINE_REQUIRED` | No |
| normalizer changed | changed | `REBASELINE_REQUIRED` | **Yes** |

A downstream ingestion workflow must treat `requires_governance_refresh=True` as an independent obligation. It must not wait for content review, rebaseline, embedding or other slower work before applying the new retrieval authorization state.

## Rationale

Content lifecycle and authorization lifecycle are different concerns. Modelling access refresh independently avoids a security-sensitive race while keeping the existing deterministic version-resolution vocabulary simple.

This is an example of a broader design rule:

> When two changes may occur concurrently and one has an independent safety obligation, do not encode them as mutually exclusive states.

## Consequences

### Positive

- simultaneous content + access changes cannot hide an ACL refresh;
- normalization migrations cannot defer new access restrictions;
- downstream orchestration has an explicit security signal;
- the canonical content-version model remains unchanged;
- regression tests now cover concurrent-change scenarios rather than only single-variable cases.

### Negative / trade-offs

- `VersionDecision` now has more than one output dimension;
- callers must handle the governance signal independently from the primary action;
- future persistence/orchestration must define ordering and atomicity for governance projection updates.

## Evidence

Implementation:

- `apps/api/src/tropos/core/application/ingestion/versioning.py`

Regression tests:

- `apps/api/tests/unit/core/application/ingestion/test_versioning.py`
  - content change + access change;
  - normalization-strategy change + access change;
  - access-only and no-change behavior.

Related decision: `ADR-004-deterministic-normalization-and-content-versioning.md`.

## Revisit when

Revisit this decision when persistence/indexing orchestration is implemented. At that point Tropos must decide how governance projection updates are made atomic or fail-closed across the canonical store and each retrieval index.
