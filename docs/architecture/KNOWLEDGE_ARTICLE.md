# Knowledge Article architecture

## Purpose

KnowledgeArticle is Tropos's canonical operational-document contract. It converts governed evidence into a stable structured artifact that Resolve can use for service resolution and that downstream capabilities can later transform without inventing a separate version of operational truth.

## Boundary

The domain contract lives in `tropos.core.domain.knowledge_article` because the artifact is reusable across capabilities. Resolve owns the business workflow that creates and consumes it; Core owns the stable artifact and evidence semantics.

```text
Governed KnowledgeChunk
        ↓
EvidenceRef
        ↓
Resolve generation workflow
        ↓
KnowledgeArticleDraft
        ├── TroubleshootingArticle
        ├── HowToArticle
        └── FAQArticle
        ↓
future review / approval
        ↓
approved operational knowledge
        ├── Resolve / NBA
        └── Training transformation
```

## Fixed article structures

### Troubleshooting

Required operational structure:
- issue description
- one or more symptoms
- prerequisites when applicable
- diagnostic checks when applicable
- one or more resolution steps
- expected result

Optional structured sections:
- exceptions
- escalation criteria
- gaps

### How-to

Required operational structure:
- purpose
- prerequisites when applicable
- one or more execution steps
- expected result

Optional structured sections:
- next steps
- exceptions
- gaps

### FAQ

Required operational structure:
- grounded introduction
- one or more structured question/answer items

Optional structured sections:
- additional information
- gaps

## Business intake and prompt-control boundary

A business user can influence the generation request, but cannot edit the system's grounding and governance rules.

```text
Business intake
    ├── subject
    ├── article type
    ├── product / module
    ├── bounded business context
    ├── retrieval keywords
    └── bounded output preferences
            ↓
KnowledgeArticleGenerationRequest
            ↓
    ┌───────┴────────┐
    ▼                ▼
Retrieval intent   Prompt inputs
    │                │
    ▼                ▼
governed retrieval  provider adapter (later)
```

### Business-editable controls

The initial contract deliberately exposes only limited controls:

- subject/problem to document;
- article type;
- product and optional module;
- short business context;
- explicit retrieval keywords;
- standard or detailed output;
- bounded focus areas;
- preferred terminology.

Article layout, audience, tone and arbitrary system-prompt text are not business controls for this artifact. Knowledge Articles remain fixed operational documents.

### System-owned controls

Tropos owns the non-editable generation policy:

- supplied evidence is required;
- missing information must be surfaced;
- conflicting evidence must be surfaced;
- unsupported claims are not allowed;
- the selected article type keeps its fixed structure;
- access-control and evidence-governance rules remain outside business prompt control.

The business-context field is treated as contextual input, not as an authority to override these rules.

### Deterministic pre-model composition

`build_retrieval_intent()` and `build_prompt_inputs()` are pure deterministic transformations of the typed request and system-selected prompt profile. This makes the exact pre-model inputs testable before a provider is introduced.

The prompt profile has a stable identifier and version so later evaluation runs can attribute behavior to a specific prompt configuration.

## Grounding rules

`EvidenceClaim` and `ArticleStep` require at least one stable `EvidenceRef`. `ArticleGap` records missing information, conflict or ambiguity with contextual evidence. Prompt-local aliases are not part of this domain model and must never be persisted as evidence identity.

## Deliberate exclusions

The current slices do not yet define:
- model/provider invocation for Knowledge Article generation;
- article rendering or visual layout;
- persistence;
- draft/review/approval lifecycle;
- publication;
- case classification or Next Best Action.

Those concerns remain separate so the article and intake contracts can be tested deterministically before runtime orchestration is introduced.
