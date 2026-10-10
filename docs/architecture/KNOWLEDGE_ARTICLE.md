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

## Grounding rules

`EvidenceClaim` and `ArticleStep` require at least one stable `EvidenceRef`. `ArticleGap` records missing information, conflict or ambiguity with contextual evidence. Prompt-local aliases are not part of this domain model and must never be persisted as evidence identity.

## Deliberate exclusions

This slice does not define:
- model/provider invocation
- article rendering or visual layout
- persistence
- draft/review/approval lifecycle
- publication
- case classification or Next Best Action

Those concerns remain separate so the article contract can be tested deterministically before runtime orchestration is introduced.
