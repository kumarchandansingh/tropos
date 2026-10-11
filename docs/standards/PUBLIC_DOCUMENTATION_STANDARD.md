# Public documentation standard

## Purpose

Tropos documentation is part of the delivered system. It records the current product and architecture, the decisions that constrain future changes, the evidence behind quality claims, and the operating controls used to evolve the repository safely.

The public documentation is written for an external engineer, architect, product leader, program leader, security reviewer, or contributor who did not participate in the original discussion. It must stand on its own without interview notes, personal context, or knowledge of the author's learning process.

## Principles

### Write for a stakeholder and a concern

Every document has an intended use. Architecture documents explain the views needed to understand or change the system. Product documents explain the user problem, capability boundary, maturity, and outcome. Decision records explain why a durable choice was made. Quality documents explain what evidence supports or limits a claim. Delivery documents explain how changes are governed.

Do not create a document only because work happened. Create it because a future stakeholder needs the information to make, review, operate, or change the system.

### Lead with purpose and current truth

State why the document exists and what system boundary it describes. Describe implemented behavior in the present tense. Label planned, deferred, experimental, and unvalidated behavior explicitly.

Documentation must not make implemented behavior look planned or planned behavior look implemented.

### Record decisions, not conclusions without context

A durable decision record must make the reasoning inspectable. It must include:

1. the problem and scope;
2. decision drivers, constraints, and relevant quality attributes;
3. credible alternatives;
4. the selected option;
5. consequences and trade-offs;
6. implementation or evaluation evidence;
7. conditions that should trigger reconsideration.

A decision is not well documented when the reader can see what was chosen but cannot understand why another competent team might have chosen differently.

### Separate evidence from assertion

Claims such as performance, accuracy, reliability, scale, security, maturity, or production readiness require evidence or a clearly stated limitation.

Use precise language:

- "implemented" means executable behavior exists in the repository;
- "evaluated" means the named subject was executed against the stated dataset or test;
- "production" refers only to a real production environment or workload;
- "scalable" is not a substitute for a stated scale, load, latency, or architecture property;
- "secure" is not a substitute for named controls and threat assumptions.

Synthetic evaluation results must be labelled as synthetic evidence and must not be presented as customer or production outcomes.

### Prefer direct technical prose

Use active voice, concrete nouns, and short sentences. Put the decision or fact before background commentary when the reader needs the decision first.

Avoid:

- rhetorical framing that answers an unstated objection;
- vague maturity adjectives such as "enterprise-grade", "world-class", or "production-ready";
- unexplained acronyms;
- marketing language in architecture and quality documents;
- personal learning commentary;
- interview, resume, recruiter, or hiring-manager guidance.

Technical terms are appropriate when they add precision. Define an acronym on first use when a reader cannot reasonably be expected to know it.

### Keep one canonical owner for each question

The documentation model is intentionally separated by purpose:

| Question | Canonical public artifact |
| --- | --- |
| What problem does Tropos solve and what works now? | Product docs and root README |
| How does the current system work? | Architecture docs and diagrams |
| Why was a durable technical choice made? | Architecture Decision Record (ADR) |
| What evidence supports a quality claim? | Quality/evaluation docs and saved reports |
| How are changes delivered and controlled? | Delivery docs |
| What changed over time? | Build history and version control |

Engineering deep dives may explain a mechanism, but they are not authoritative for implementation status.

## Architecture documentation expectations

Architecture descriptions should make the relevant stakeholder concerns explicit. A useful architecture document normally identifies:

- scope and system boundary;
- responsibilities and ownership boundaries;
- important components and interfaces;
- data, control, or dependency flow;
- trust, security, lifecycle, or failure boundaries when relevant;
- current constraints and known limitations;
- links to the decision records that explain durable choices.

A diagram is evidence of structure only when its labels and surrounding text explain the view being shown. Decorative diagrams do not substitute for an architecture description.

## Decision-record standard

New or materially revised ADRs must use this structure:

```text
Context
Decision drivers and constraints
Options considered
Decision
Consequences
Evidence
Revisit when
```

The decision statement uses direct present-tense language such as "Tropos uses..." or "Tropos keeps...". Accepted ADRs remain historical records. A later change supersedes an ADR; it does not rewrite history.

## Public/private boundary

The public repository may contain engineering explanations and design rationale. It must not contain material whose purpose is personal interview preparation, resume positioning, recruiter messaging, or private career reflection.

A useful decision may appear in both contexts, but the public artifact is written as a system record:

```text
Private note:
"This could be a TPM trade-off story."

Public record:
"Retrieval assurance precedes benchmark expansion because mutation evidence
showed that release-critical semantics were not yet protected consistently."
```

Interview preparation consumes public engineering evidence later. Interview preparation is not a source-of-truth documentation layer.

## Documentation impact for code changes

A material pull request must either update the authoritative public documentation it changes or record an explicit documentation-impact rationale in the pull request.

Examples:

| Change | Expected public record |
| --- | --- |
| Product capability or user-visible behavior | Product status and/or architecture |
| Component/interface/data-flow change | Architecture and, when durable, ADR |
| Evaluation semantics, dataset, grader, or gate | Quality/evaluation documentation |
| CI, release, environment, or delivery control | Delivery documentation and, when durable, ADR |
| Durable technical choice | ADR |
| Implementation with no public semantic change | Explicit "documentation impact is N/A" rationale |

The N/A path is an auditable exception, not the default.

## CI-enforced checks

The documentation governance check enforces deterministic rules:

- material pull requests leave an authoritative documentation change or an explicit N/A rationale;
- changed ADRs contain the required decision sections;
- public Markdown has a top-level title;
- interview/private meta-language is absent from the public documentation surface.

CI cannot reliably judge whether reasoning is insightful, whether an alternative is genuinely credible, or whether evidence is sufficient for a business decision. Those remain review responsibilities. The deterministic gate prevents known structural failures from recurring.

## Review questions

A reviewer should be able to answer these questions from the documentation:

1. Who is this document for and what decision or task does it support?
2. Is the described state implemented, experimental, planned, or deferred?
3. What constraint or quality attribute drove the design?
4. Which alternatives were credible?
5. What does the selected option give up?
6. What evidence supports the claim?
7. What is still unresolved?
8. What condition should trigger a new decision?

## References

This standard is informed by established public guidance rather than a Tropos-specific writing convention:

- [ISO/IEC/IEEE 42010:2022 — Architecture description](https://www.iso.org/standard/74393.html), which structures architecture descriptions around architectural concepts, viewpoints, and concerns.
- [SEI — A Structured Approach for Reviewing Architecture Documentation](https://www.sei.cmu.edu/library/a-structured-approach-for-reviewing-architecture-documentation/), which centers architecture documentation review on stakeholder usefulness.
- [SEI — Views and Beyond](https://www.sei.cmu.edu/library/views-and-beyond-collection/), which treats documentation as an output of architecture work rather than an unrelated follow-on activity.
- [AWS Prescriptive Guidance — Architectural decision record process](https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/adr-process.html), which emphasizes context, decision, consequences, lifecycle, ownership, and decision history.
- [GitHub Docs — Content design principles](https://docs.github.com/en/contributing/writing-for-github-docs/content-design-principles), which emphasizes user needs, clarity, correctness, consistency, and purposeful content.
- [Microsoft Writing Style Guide](https://learn.microsoft.com/style-guide) and [Google developer documentation style guide](https://developers.google.com/style), which favor direct, clear, accessible technical prose.
