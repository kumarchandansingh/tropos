# ADR-003: Protected main with required CI

**Status:** Accepted  
**Date:** 2026-09-20

## Context

Tropos is a public repository and is being built with AI-assisted development as well as manual changes. The project needs an integration path that does not depend on remembering local checks or on the repository owner manually following a convention.

The repository already had deterministic quality checks, but a process is not a control until GitHub enforces it.

## Options considered

### 1. Direct pushes to `main` with optional local testing

Lowest friction, but easy to bypass accidentally and weak as public engineering evidence.

### 2. PR workflow by convention only

Better reviewability, but the owner can still bypass it and CI can be skipped.

### 3. Protected `main` with required PR and required `api-quality`

Make the delivery policy enforceable in the repository itself.

## Decision

Tropos will use a protected `main` branch and a PR-based integration workflow.

The current required quality check is `api-quality`. The CI workflow runs on every pull request so the required check is always created, including for documentation-only changes.

The configured branch policy also requires conversation resolution and disables the normal owner/admin bypass; force pushes and branch deletion are not enabled.

Approving reviewers are not required while the repository has a single maintainer.

## Rationale

The strongest low-cost control for the current project is a repeatable automated integration gate. It provides executable evidence that every integrated change passes the agreed formatter, linter, type checker, unit tests and package build.

Running the workflow for every PR avoids the failure mode where path filters prevent a required check from appearing.

## Consequences

### Positive

- direct integration into `main` is blocked by policy;
- every PR receives the same shared quality check;
- the project demonstrates a real CI discipline rather than documentation-only intent;
- failures are visible before integration;
- protected `main` becomes a reliable base for future deployment automation.

### Negative / trade-offs

- even docs-only PRs currently run the Python quality job;
- the owner cannot intentionally bypass the rule without changing repository settings;
- no mandatory second-person review exists while the project is solo-maintained.

## Evidence

- `.github/workflows/ci.yml`
- `.github/pull_request_template.md`
- GitHub branch metadata reports `main` as protected;
- `api-quality` is configured as a required status check with enforcement level `everyone`;
- PR #5 removed the earlier path filters so the gate runs on every PR.

The `api-quality` job currently executes:

1. dependency sync with `uv sync --dev --locked`;
2. Ruff format check;
3. Ruff lint;
4. strict mypy over `src` and `tests`;
5. pytest;
6. package build.

## Revisit when

Revisit the rule when:

- additional maintainers join and reviewer approval becomes meaningful;
- CI is decomposed into multiple required jobs;
- AI/RAG evals become executable release gates;
- deployment environments introduce additional promotion checks;
- docs-only CI cost becomes material enough to justify an always-present lightweight gate plus path-aware specialist jobs.
