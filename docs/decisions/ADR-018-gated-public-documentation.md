# ADR-018: Treat public documentation as a gated delivery artifact

**Status:** Accepted  
**Date:** 2026-10-11

## Context

Tropos uses repository documentation to communicate product state, architecture, durable decisions, evaluation evidence, and delivery controls. That documentation has not always evolved at the same pace as the implementation.

Two failure modes became visible:

1. current-state documentation could remain stale after executable capability changed; and
2. engineering reasoning could be recorded in author-oriented learning material instead of being reframed as a stakeholder-facing system record.

The root README, for example, continued to describe lexical retrieval and evaluation as planned after BM25, dense retrieval, hybrid ranking, and retrieval evaluation had been implemented. The pull-request template asked authors to consider documentation impact, but CI did not verify that the public record changed with material code or delivery changes.

Documentation therefore represented an uncontrolled dependency in the change process: code could pass its automated gates while leaving the repository's public description inconsistent with the executable system.

## Decision drivers and constraints

The documentation control must satisfy these concerns:

- **correctness:** current-state documents must not contradict executable behavior;
- **traceability:** durable decisions must preserve context, credible alternatives, consequences, evidence, and revisit conditions;
- **stakeholder usability:** a reader who did not participate in the original discussion must be able to understand the system and the intent behind a decision;
- **separation of concerns:** product state, living architecture, decisions, quality evidence, delivery controls, and engineering deep dives have distinct canonical purposes;
- **public/private boundary:** personal career material and author-oriented preparation must not be part of the public documentation model;
- **low operational cost:** the first control should use repository-native, deterministic checks rather than require a hosted documentation platform or model call on every pull request;
- **reviewability:** CI should enforce objective structure and change discipline without pretending to judge architectural insight mechanically.

The approach follows the stakeholder/concern orientation of ISO/IEC/IEEE 42010 and SEI architecture-documentation guidance, the context/decision/consequence lifecycle used by AWS ADR guidance, and the clarity and content-model principles published by GitHub, Microsoft, and Google.

## Options considered

### 1. Keep documentation as a review-only checklist

The pull-request template already contains a documentation-impact checklist.

This has minimal implementation cost, but it relies on memory and reviewer discipline. It did not prevent known drift because a pull request could merge while the relevant box remained informational rather than enforced.

### 2. Require any Markdown change for every code change

This is easy to automate.

It creates weak compliance: an unrelated Markdown edit can satisfy the control, minor implementation changes generate unnecessary documentation churn, and the gate does not distinguish authoritative product/architecture records from explanatory notes.

### 3. Gate material changes on authoritative documentation or an explicit exception

CI classifies material product/architecture, evaluation, and delivery changes. Each class must update an appropriate authoritative documentation surface or provide an explicit pull-request rationale explaining why documentation impact is N/A.

CI also checks objective public-documentation rules such as required decision-record structure and absence of private preparation language.

### 4. Use an LLM documentation reviewer as the release gate

A model can assess framing, completeness, and prose quality beyond deterministic checks.

This introduces model cost, nondeterminism, prompt/version governance, and a new failure mode into the base integration path. It is also unsuitable as the sole authority for whether a durable architecture record is complete.

## Decision

Tropos uses option 3.

Documentation governance becomes part of the existing required CI job. A material pull request must either:

- update an authoritative product, architecture, quality, delivery, standards, or decision record appropriate to the changed system boundary; or
- explicitly mark documentation impact as N/A and provide a substantive rationale in the pull request.

The repository also defines a public documentation standard. CI enforces deterministic portions of that standard:

- public Markdown starts with a top-level title;
- private career/preparation language is excluded from the public documentation surface;
- changed Architecture Decision Records (ADRs) contain the required decision sections;
- material pull-request changes have an authoritative documentation update or an audited exception.

Semantic quality remains a review responsibility. CI does not score whether an alternative is intellectually strong, whether evidence is sufficient for a business decision, or whether prose demonstrates architectural judgment.

## Consequences

### Positive

- documentation impact becomes a delivery control rather than a reminder;
- a code-complete change cannot silently leave the public system description stale without an explicit exception;
- durable decisions gain a consistent evidence and revisit structure;
- public documents are organized around stakeholder use rather than the author's learning process;
- private career-preparation language is prevented from re-entering the public documentation surface;
- the control runs without external services, model credentials, or additional Python dependencies.

### Negative / trade-offs

- pull requests that change material implementation now carry additional documentation work;
- path-based classification cannot determine semantic impact perfectly, so some changes may require an N/A justification;
- deterministic checks can verify structure but not depth, accuracy of reasoning, or quality of technical writing;
- existing historical documentation is not automatically upgraded to the new decision-record structure unless it is materially revised;
- broadening the gate too aggressively could create documentation churn, so accepted document categories and exception behavior need periodic review.

## Evidence

This decision is implemented through:

- `scripts/check_public_docs.py`, which performs the deterministic governance checks;
- `.github/workflows/ci.yml`, which runs the documentation check inside the required CI job;
- `.github/pull_request_template.md`, which records documentation impact and the N/A rationale;
- `docs/standards/PUBLIC_DOCUMENTATION_STANDARD.md`, which defines the public content model and writing standard;
- the refreshed root `README.md` and documentation index, which reconcile previously stale implementation status;
- removal or reframing of public material whose purpose was personal preparation rather than system documentation.

The control is independently testable by changing a material implementation path without a documentation update and verifying that the pull-request CI job fails unless an explicit documentation-impact exception is recorded.

## Revisit when

Revisit this decision when one of these conditions is observed:

- false-positive documentation failures become common enough to slow routine maintenance;
- repository scale requires ownership-aware rules such as CODEOWNERS or documentation-area reviewers;
- public documentation volume justifies automated link, terminology, or content-model validation beyond the current structural checks;
- a model-based documentation reviewer can be calibrated against human review and adds measurable value without becoming the sole release authority;
- the repository moves to a hosted documentation platform whose build or publishing pipeline becomes the more appropriate enforcement point.
