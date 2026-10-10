## Problem
What user, product, reliability, quality, or engineering problem does this change solve?

## Architecture impact
Which domain, application, port, adapter, data, retrieval, evaluation, delivery, or product boundary changes?

## Decision
What approach was selected?

## Alternatives and trade-offs
What realistic alternatives were considered? What does the selected option give up?

## Revisit trigger
What evidence, scale, failure mode, or product requirement would make this decision worth reconsidering?

## Scope
What changed?

## Out of scope
What is deliberately not changing?

## Expected behavior
What should be true after this change?

## Validation
- [ ] `uv run ruff format --check .`
- [ ] `uv run ruff check .`
- [ ] `uv run mypy src tests`
- [ ] `uv run pytest`
- [ ] `uv build`
- [ ] Relevant integration tests, if applicable
- [ ] Relevant AI/RAG evals, if applicable

## Evidence
Add test output, screenshots, example records, evaluation comparison, or other evidence appropriate to the change.

## Risks / follow-ups
What is intentionally deferred, risky, or worth watching after merge?

## Documentation impact
Mark each relevant item. Use N/A only when the change genuinely does not affect that documentation layer.

- [ ] Product/capability status updated
- [ ] Living architecture/codebase map updated
- [ ] Quality/evaluation documentation updated
- [ ] Build history updated for a material delivered slice
- [ ] Backlog/status updated where delivery state changed
- [ ] ADR added/updated for a durable architecture decision
- [ ] Decision/trade-off learning material updated when reusable reasoning changed
- [ ] Documentation impact is N/A

A material build is not complete when code/tests merge but product state, architecture state, or a durable decision remains stale in documentation.
