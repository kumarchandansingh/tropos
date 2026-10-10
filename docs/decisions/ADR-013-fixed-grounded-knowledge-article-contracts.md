# ADR-013: fixed grounded Knowledge Article contracts

Status: accepted for the first Resolve Knowledge Article slice.

## Context

Tropos needs an operational artifact above governed chunks that can be reviewed, reused by Resolve, and later transformed into Training content. Letting a model invent article shape on every run would make evaluation, publishing and downstream consumption unstable. The artifact must also preserve the stable EvidenceRef boundary introduced for grounded generation.

## Decision

Define KnowledgeArticleDraft as a shared core-domain contract rather than a Resolve-only model. Support three controlled article types initially: troubleshooting, how-to and FAQ. Each type has a fixed typed content structure and evidence-bearing claims or steps. Article type must match the supplied content template.

Every factual claim or action represented by EvidenceClaim or ArticleStep requires at least one stable EvidenceRef. Missing, conflicting or ambiguous source information is represented explicitly as ArticleGap with contextual evidence. Rendering and visual layout remain outside the domain model.

Resolve is the first capability expected to create and consume KnowledgeArticleDraft. Training may later transform approved Knowledge Articles into audience-specific artifacts without redefining operational truth.

## Alternatives and costs

A single generic section list would be more flexible but would weaken schema validation and make article-specific evaluation harder. Keeping KnowledgeArticle inside Resolve would simplify ownership initially but would couple a reusable operational artifact to one capability. Allowing arbitrary model-generated layouts would reduce coding effort but create unstable outputs and brittle downstream behavior.

The fixed model is intentionally narrow. It does not yet define publishing status, approval lifecycle, persistence, provider calls or presentation templates.

## Revisit

Expand article types only when a real use case requires them. Revisit shared claim abstractions after multiple capabilities demonstrate common semantics. Add lifecycle/versioning separately so content structure does not become entangled with review state.