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
local immutable review submission (GOV-101A)
        ↓
human approval / changes requested, with audit events
        ↓
future publication of approved operational knowledge
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
governed retrieval  generator port
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

## Grounded generation runtime

`GenerateKnowledgeArticle` is the application service that triggers retrieval and generation.

```text
KnowledgeArticleGenerationRequest
            ↓
build retrieval intent
            ↓
deterministic retrieval query
            ↓
KnowledgeChunkRetriever.search
            ↓
authorized RetrievedKnowledgeChunk[]
            ↓
KnowledgeArticleEvidenceExcerpt[]
  text + stable EvidenceRef
            ↓
KnowledgeArticleGenerator port
            ↓
LangChain adapter
            ↓
temporary prompt aliases
E1 → EvidenceRef A
E2 → EvidenceRef B
            ↓
structured model output
            ↓
deterministic alias resolver
            ↓
KnowledgeArticleDraft
with stable EvidenceRef objects
```

The generator port is framework-independent. The LangChain adapter is infrastructure at the capability edge and accepts an injected model. Tests use fake structured models, so this slice requires no network call or provider credentials.

### Retrieval trigger

The runtime query is built deterministically from the request subject, product, optional module and explicit retrieval keywords. Tenant and group access context is passed to the existing governed retrieval boundary. Business context is not used as an uncontrolled retrieval query.

No authorized evidence means generation stops with a `LookupError`; the model is not called.

### Prompt-local evidence aliases

Only temporary aliases such as `E1` and `E2` are shown to the model. They exist only for one invocation.

The model returns those aliases in its structured output. Tropos resolves them exactly to the corresponding stable `EvidenceRef` before constructing the domain artifact. Unknown aliases fail deterministically; aliases are never persisted as evidence identity.

This proves citation identity and provenance, not semantic entailment. Whether a cited chunk actually supports a claim remains an evaluation concern.

## Grounding rules

`EvidenceClaim` and `ArticleStep` require at least one stable `EvidenceRef`. `ArticleGap` records missing information, conflict or ambiguity with contextual evidence. Prompt-local aliases are not part of this domain model and must never be persisted as evidence identity.

## Decisions and trade-offs

| Decision | Selected approach | Cost / downside | Revisit trigger |
| --- | --- | --- | --- |
| Article structure | Fixed troubleshooting/how-to/FAQ contracts | less free-form flexibility | a distinct repeatable operational document type is proven necessary |
| Business control | Typed bounded preferences | no arbitrary system-prompt editing | governed prompt/template administration becomes a product requirement |
| Evidence identity | Stable EvidenceRef outside the prompt | projection/resolution step required | direct stable-reference model interfaces become reliably usable |
| Model framework | LangChain adapter behind Tropos port | Tropos maintains adapter code | framework capability materially reduces cost without taking over domain semantics |
| Missing/conflicting information | Typed gaps rather than invented completion | drafts can remain explicitly incomplete | reviewed business policy resolves the missing/conflicting source |
| Semantic support | Separate evaluator concern | alias validity alone is insufficient | calibrated semantic judge/human review is added |

See [ADR-013](../decisions/ADR-013-fixed-grounded-knowledge-article-contracts.md), [ADR-016](../decisions/ADR-016-stable-evidence-references-with-model-local-aliases.md), and [ADR-017](../decisions/ADR-017-bounded-business-generation-controls.md).

## Review lifecycle: GOV-101A revisioned local foundation

This implementation is aligned to the entity/key strategy proposed in
[DATA-101 (PR #118)](https://github.com/kumarchandansingh/tropos/pull/118):
`knowledge_articles` identifies an article within a tenant;
`article_revisions` stores its immutable numbered snapshots; `article_citations`
indexes every evidence reference by claim path; and `review_events` stores
ordered submission/approval/change-request decisions.

Submitting an initial `KnowledgeArticleDraft` requires `tenant_id`,
`article_id`, `submitted_by`, and `expected_previous_revision=0`.
A new version requires the exact previous revision number and its review to
have reached `APPROVED` or `CHANGES_REQUESTED`. Each revision preserves
its canonical JSON and SHA-256, and its citations are frozen on submission.
Approval of revision 1 never approves revision 2. Reviews use
`expected_event_seq`, independent of `revision_no`, to reject stale decisions
and duplicate reviews. SQLite transactions serialize new revisions and decisions;
database triggers enforce event order, separation of duties and immutability.

Local reads are scoped by `(tenant_id,article_id,revision_no)`; the original
revision and all review events remain available after later submissions.
Payload/citation consistency is checked on read and before approval.

**This is not a production authorization boundary.** Tenant IDs, submitter IDs
and reviewer IDs are caller-asserted. It has no verified principals, role
assignment or authenticated tenant membership, and its citation index is not
yet foreign-keyed to a source chunk table. The `source_evidence_set_id` is a
nullable lineage field until governed evidence-set persistence exists.
A previously created unscoped `article_reviews` table is rejected explicitly:
assigning a tenant to historical approvals requires a deliberate migration,
not an invented or silent mapping.

This slice covers local approval and resubmission contracts, not a browser
review queue or publication. `APPROVED` is not `PUBLISHED`.
Before a hosted API ships, introduce verified tenant/principal and citation
authorization, plus publication/read-time source freshness validation.
The DATA-101 greenfield schema is a reference design, **not an in-place migration**.

Regression tests cover multi-revision resubmission, tenant-key isolation,
duplicate/stale attempts, self-review, mandatory rejection notes, full
payload/citation integrity and SQLite guardrails.

## Deliberate exclusions

The current slices do not yet define:
- live provider/model configuration or credentials;
- semantic grounding evaluation for Knowledge Articles;
- article rendering or visual layout;
- hosted article persistence and production access control;
- authenticated review API and reviewer UI;
- publication;
- case classification or Next Best Action.

Those concerns remain separate so generation behavior can be evaluated before lifecycle and product-surface work is introduced.
