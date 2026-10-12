# Delivery Metrics Automation on Protected Main

Status: Design for implementation

## User / business problem

The Delivery Metrics workflow correctly regenerates `docs/product/delivery-metrics.md`, but then attempts to push directly to `main`.

The repository protects `main` with:
- required pull requests;
- required `api-quality` status checks.

The workflow therefore fails after successful metric generation. This produces a red workflow even though the generated metrics are valid.

## Analogous patterns reviewed

- Dependabot: automated repository changes are proposed through pull requests rather than bypassing branch protection.
- Renovate: generated dependency updates are maintained on bot-owned branches and refreshed through pull requests.
- GitHub protected-branch workflows: automation should respect the same review/status-check boundary as human changes.

Tropos should follow the same pattern for generated delivery metrics.

## Information architecture / UX

No product UI change.

The operational artifact remains:
- `docs/product/delivery-metrics.md`

The workflow becomes:
- generate metrics;
- if unchanged, exit successfully;
- if changed, update a dedicated automation branch;
- open a pull request if one does not already exist;
- subsequent runs refresh the same branch / PR.

## Data / domain audit

No domain model changes.

Existing inputs:
- GitHub issues;
- pull requests;
- deployments;
- delivery-metrics config.

Existing output:
- generated Markdown report.

New operational object:
- automation branch + PR only; no new application data model.

## Functional architecture

    event / schedule
      → checkout main
      → generate metrics
      → no diff? success
      → diff?
           → commit on automation/delivery-metrics
           → push automation branch
           → existing open PR?
                yes → refresh branch only
                no  → create PR to main

## Security

- Use `GITHUB_TOKEN` only.
- Grant `contents: write` and `pull-requests: write`.
- Do not bypass branch protection.
- Do not force-push `main`.
- Automation branch may be force-updated because it is machine-owned and disposable.
- Generated metrics contain repository delivery data only.

## Failure / recovery states

- Metrics unchanged → workflow succeeds with no PR.
- Existing automation PR → branch is refreshed; no duplicate PR.
- Branch push fails → workflow fails visibly.
- PR creation fails → workflow fails visibly while main remains untouched.
- Main advances → next run regenerates from the latest default branch and refreshes the automation branch.

## Acceptance evidence

1. workflow no longer pushes directly to `main`;
2. workflow has pull-request write permission;
3. unchanged metrics exit successfully;
4. changed metrics are committed to `automation/delivery-metrics`;
5. an existing open PR is reused;
6. a missing PR is created automatically;
7. branch protection remains fully enforced;
8. workflow shell is syntax-valid and CI/docs governance stay green.

## Deferred

- auto-merge after checks;
- bot labels/assignees;
- signed commits;
- GitHub App identity instead of `GITHUB_TOKEN`;
- delivery-metrics publication outside the repository.
