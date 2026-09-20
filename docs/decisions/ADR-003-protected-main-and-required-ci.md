# ADR-003: Protected main with required CI

**Status:** Accepted  
**Date:** 2026-09-20

## Context

Tropos needs a repeatable integration path that does not depend on local checks or maintainer convention. The repository already has deterministic quality checks; branch protection makes those checks enforceable before code reaches `main`.

## Options considered

### Direct pushes to `main`

Lowest friction, but quality checks can be bypassed accidentally.

### Pull requests by convention

Improves reviewability, but does not enforce CI or prevent direct integration.

### Protected `main` with required pull request and CI

Use repository rules to require the integration workflow.

## Decision

Tropos uses a protected `main` branch and pull-request-based integration.

The required status check is `api-quality`. The workflow runs on every pull request so the check exists consistently, including for documentation-only changes.

Conversation resolution is required. Force pushes and branch deletion are disabled by the branch policy. Approving reviewers are not required while the repository has a single maintainer.

## Consequences

### Positive

- Changes cannot bypass the shared quality gate under normal repository operation.
- Every pull request receives the same integration check.
- `main` is a reliable base for future release automation.
- Formatting, lint, type, test, and package-build failures are visible before integration.

### Negative / trade-offs

- Documentation-only changes still run the Python quality job.
- Changing an emergency policy requires changing repository rules rather than bypassing them.
- No second-person approval exists while the repository has one maintainer.

## Evidence

- `.github/workflows/ci.yml`
- `.github/pull_request_template.md`
- protected `main`
- required `api-quality` check

The job runs:

1. `uv sync --dev --locked`;
2. `ruff format --check`;
3. `ruff check`;
4. `mypy src tests`;
5. `pytest`;
6. `uv build`.

## Revisit when

Revisit the rule when additional maintainers make reviewer approval meaningful, CI is split into multiple required jobs, AI/RAG evaluations become executable release gates, or deployment environments introduce promotion checks.
