# ADR-016: stable evidence references with model-local aliases

**Status:** Accepted  
**Date:** 2026-10-10

## Context

Grounded generation needs model outputs to cite supplied evidence. Prompt-local ordinal identifiers are easy for a model to copy, but they are not durable provenance. Conversely, exposing long internal identifiers directly to the model increases output-copying risk and leaks infrastructure identity into prompt contracts. Tropos also needs model-framework portability.

## Options considered

1. Persist model-returned prompt ordinals such as `1` or `E1`.
2. Require the model to return full stable internal evidence identifiers directly.
3. Let the model generate without citations and attach evidence afterward.
4. Project stable `EvidenceRef` objects into temporary prompt aliases, then resolve aliases exactly after model output.

## Decision

Use a two-layer evidence identity:

- Tropos creates stable `EvidenceRef` objects from governed retrieved chunks;
- each model invocation maps them to temporary aliases such as `E1`, `E2`;
- the structured model output may cite only supplied aliases;
- Tropos resolves aliases through an exact deterministic mapping;
- unknown aliases fail; aliases are never persisted as durable evidence identity;
- final domain artifacts contain stable `EvidenceRef` objects.

Model execution frameworks such as LangChain remain adapters behind Tropos-owned generation/extraction ports.

## Why

This combines simple model citation behavior with stable lineage and avoids post-hoc citation attachment. Exact resolution is a deterministic governance invariant and does not require semantic search, fuzzy matching, or another model call.

## Consequences

### Positive

- persisted artifacts remain traceable to stable governed evidence;
- models cannot invent a valid citation identifier outside the supplied set;
- provider/framework changes do not alter domain evidence identity;
- citation validation is cheap and deterministic.

### Negative / trade-offs

- every invocation needs an alias projection/resolution step;
- a valid alias does not prove that the cited evidence semantically supports the claim;
- semantic groundedness still requires deterministic expectations, model/human evaluation, or other evidence.

## Evidence

- PR #32: first structured Training extraction
- PR #34: stable evidence-backed Training artifacts
- PR #66: grounded Knowledge Article generation
- `tropos.core.domain.evidence.EvidenceRef`
- Training and Knowledge Article adapter/tests

## Revisit when

- structured model/tool interfaces reliably carry durable references directly without reducing output reliability;
- claim-level evidence graphs become a proven shared requirement across multiple capabilities;
- semantic-support verification needs a dedicated verifier layer.

