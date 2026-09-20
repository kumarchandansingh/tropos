# Tropos release-readiness checklist

Use this checklist for a deployable release candidate. Mark an item complete only when its evidence
is linked from the release record. `N/A` requires a short rationale and an accountable approver.

## Release identity

- [ ] Scope and user outcome are stated.
- [ ] Release ID, commit SHA, and immutable artifact digest are recorded.
- [ ] Runtime, dependency lockfile, configuration, migration, and index versions are recorded.
- [ ] Change log and known limitations are complete.

## Build and verification

- [ ] Formatting and lint checks pass.
- [ ] Static type checks pass.
- [ ] Unit and integration tests pass.
- [ ] Full regression suite passes.
- [ ] Security and dependency checks pass.
- [ ] AI/retrieval evaluations meet declared thresholds where applicable.
- [ ] Documentation and operational impacts are reviewed.

## Data and governance

- [ ] Environment data is permitted, separated, and appropriately masked.
- [ ] Tenant and group access tests pass.
- [ ] Provenance and citation-integrity tests pass.
- [ ] Migration is backward compatible.
- [ ] Backup and restore steps have current evidence.
- [ ] New index generation is parallel and the previous generation is retained.

## UAT and business readiness

- [ ] UAT entry criteria are met.
- [ ] Critical business scenarios pass with evidence.
- [ ] Defects are fixed or explicitly accepted.
- [ ] Product owner records acceptance.
- [ ] User guidance, support process, and pilot cohort are ready.

## Cutover and operations

- [ ] Cutover steps, timings, dependencies, and owners are confirmed.
- [ ] Monitoring covers health, errors, latency, access leakage, and quality.
- [ ] Alert thresholds and go/no-go thresholds are agreed.
- [ ] On-call and escalation contacts are available.
- [ ] Rollback target, authority, trigger, and estimated duration are confirmed.
- [ ] Rollback or recovery rehearsal has current evidence.
- [ ] Hypercare window and status cadence are scheduled.

## Go/no-go record

| Decision field | Value |
| --- | --- |
| Decision | Go / Conditional go / No-go |
| Time | |
| Product owner | |
| Engineering lead | |
| Release owner | |
| Operations owner | |
| Accepted risks | |
| Conditions | |
| Rollback target | |

## Post-release closure

- [ ] Smoke tests pass in Production.
- [ ] Pilot metrics remain within thresholds.
- [ ] Incidents and deviations are documented.
- [ ] Release is accepted or rolled back explicitly.
- [ ] Follow-up actions have owners and due dates.
- [ ] Lessons are added to the strategy, runbook, tests, or evaluations.
