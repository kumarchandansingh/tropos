# ADR 0001: Maintain living product architecture as docs-as-code

- Status: Accepted
- Date: 2026-09-20
- Decision owners: Product and engineering

## Context

Tropos will evolve across ingestion, parsing, chunking, indexing, retrieval, evaluation, and
human-governance capabilities. A standalone whiteboard is useful for workshops but can drift
from the implemented contracts because it is reviewed and versioned separately from code.

## Decision

Maintain the authoritative logical model and capability status in version-controlled Markdown
with Mermaid diagrams. Changes are reviewed through the same pull-request process as code.

Miro, FigJam, or similar tools may be used for discovery workshops and stakeholder facilitation,
but they are not the system of record for implemented architecture.

## Consequences

### Benefits

- architecture changes have authorship, review, and history;
- diagrams remain close to the contracts they describe;
- implementation and documentation can change atomically;
- reviewers can identify governance, migration, and compatibility impacts;
- GitHub renders the diagrams without a separate design-tool license.

### Trade-offs

- Mermaid is less flexible than a free-form whiteboard;
- complex workshop exploration may still require Miro or FigJam;
- documentation quality depends on enforcing the update policy during review.

## Operating rule

A pull request that changes knowledge-processing entities or lifecycle behavior is incomplete
until it updates the living model or explicitly explains why no documentation change is needed.
