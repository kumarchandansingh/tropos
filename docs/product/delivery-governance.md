# Tropos Delivery Governance

Status: Baseline v1  
Owner: Product / Program Management  
Applies to: Tropos product and engineering delivery

## Purpose

This document defines how sprint scope, blockers, delivery metrics, and release planning are governed. It complements the master product backlog and engineering quality gates.

## Sprint planning

A sprint has a stated goal, a planned set of stories, and a forecast capacity based on demonstrated team velocity and known availability. Story points are a relative planning measure and are not converted to hours.

A story is considered committed only when it is sufficiently refined, estimated, dependency-checked, and accepted into the sprint plan.

## In-sprint scope change

Sprint scope is protected by default. New work is triaged before it is added to a sprint.

A new item is classified as a production/quality defect, regulatory/security/compliance requirement, urgent business-critical change, or normal enhancement. Normal enhancements remain in the product backlog for future prioritization. Urgent items may enter the current sprint only after an explicit product decision.

When urgent work is accepted, one of the following is recorded:

- equivalent lower-priority scope is removed;
- sprint scope is explicitly increased and the forecast is re-baselined;
- the item is split to the minimum viable slice required for the sprint goal.

Scope additions and removals remain visible in delivery metrics so burndown and sprint-review data remain interpretable.

## Blocker management

A blocker is recorded against the affected story as soon as it is known. The delivery record identifies the blocker, affected dependency, accountable owner, source, date identified, target resolution or escalation path, and impact on the sprint goal.

Teams continue work on unblocked items where possible. A blocker that threatens the sprint goal is escalated and the sprint forecast is revised immediately.

Story points are not reduced because a story is partially complete. Unfinished work returns to the backlog and is re-planned. Only work meeting the Definition of Done and accepted counts toward velocity.

## Burndown

Burndown tracks remaining accepted sprint scope over time. It reflects baseline scope, approved scope changes, completed accepted work, and remaining scope.

An upward movement is valid when approved scope is added. A flat period may indicate work in progress, blocked work, or work not yet accepted; the chart is interpreted together with the blocker and scope-change record.

## Velocity

Velocity is the sum of story points for work completed and accepted in a closed sprint. It is used for team-level forecasting under reasonably stable conditions and is not an individual productivity metric.

After at least three completed sprints, the rolling average is used as an initial planning reference and adjusted for team availability, material dependencies, incident/support load, technical-risk work, and the sprint goal.

## Sprint review

The sprint review records original planned scope, scope added or removed, completed accepted story points, unfinished work returned to backlog, material blockers, sprint-goal outcome, quality results, release-gate status, and decisions affecting future prioritization.

## Retrospective and continuous improvement

Material delivery failures, avoidable blockers, escaped defects, and recurring planning variance result in an explicit improvement action. Where a software or AI failure is reproducible, it is added to the regression suite when appropriate.

## Metric ownership

The repository-generated delivery metrics are derived from GitHub issue metadata and the sprint calendar in `docs/product/sprint-plan.json`. The generated metrics file is `docs/product/delivery-metrics.md`.

Metrics are reporting inputs, not substitutes for product judgement. Product priority, release readiness, and quality acceptance remain explicit accountable decisions.
