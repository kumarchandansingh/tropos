# Tropos

**Every resolution strengthens the next.**

Tropos is a governed knowledge-management system that learns from resolved support cases.

Its first product capability, **Tropos Resolve**, evaluates a resolved case and recommends one knowledge action:

- `REUSE` — existing knowledge adequately resolves the case
- `IMPROVE` — relevant knowledge exists but needs correction or clarification
- `CREATE` — no adequate knowledge exists
- `NO_ACTION` — the case should not change the knowledge base

## Business problem

Support teams resolve valuable problems every day, but the knowledge created during resolution is often lost, duplicated, outdated, or difficult to retrieve.

Tropos converts case resolution into a measurable knowledge-improvement process.

## MVP workflow

1. A support case changes to `Resolved`.
2. Tropos validates that sufficient closure evidence exists.
3. Tropos retrieves related knowledge.
4. Tropos recommends a knowledge action.
5. Tropos records its evidence and reasoning.
6. A human reviewer approves, edits, or rejects the recommendation.
7. Approved knowledge is indexed for future retrieval.
8. Evaluation checks whether the knowledge loop improved.

## MVP users

- Support agent
- Knowledge reviewer
- Knowledge-management or support manager

## MVP boundaries

Tropos will initially:

- Process one canonical resolved-case format
- Search a controlled knowledge collection
- Produce evidence-backed recommendations
- Keep humans responsible for publication
- Record decisions for evaluation and audit

Tropos will not initially:

- Send customer communications
- Publish knowledge automatically
- Modify source systems automatically
- Replace support-agent judgment
- Support every connector or content format

## Engineering principles

- Business rules live in the domain layer.
- Use cases depend on interfaces, not infrastructure implementations.
- External systems connect through adapters.
- Prompts are versioned separately from application logic.
- AI outputs are structured, validated, and traceable.
- New data sources should not require changes to core business logic.
- Tests and evaluations are product capabilities, not release afterthoughts.
- Production changes must support controlled rollout and rollback.

## Planned architecture

Tropos starts as a modular monolith with clear internal boundaries:

- `domain` — business concepts and rules
- `application` — use cases and ports
- `adapters` — source, persistence, retrieval, and AI implementations
- `presentation` — HTTP and other delivery mechanisms
- `evaluation` — deterministic and AI-quality measurement
- `bootstrap` — dependency wiring

The web application will be added after the core knowledge loop works.

## Delivery approach

Development progresses through small, verifiable releases:

1. Foundation and deterministic decision baseline
2. Ingestion, indexing, retrieval, and citations
3. Knowledge-action recommendations
4. Governed drafting and human review
5. UAT, cutover, observability, and rollback readiness
6. Assisted production pilot

## Current status

Repository foundation is being established. No product capability is implemented yet.
