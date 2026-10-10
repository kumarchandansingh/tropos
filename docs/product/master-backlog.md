# Tropos Master Product & Quality Backlog

Status: Baseline v1  
Purpose: Single source of truth for sequencing Tropos platform and capability work.  
Delivery model: small verifiable PRs, explicit architecture boundaries, automated quality gates, evidence captured with each slice.

## Prioritization model

- **P0** — required to prove the current Resolve product thesis or quality foundation.
- **P1** — required next for production-like operation, scale, or broader capability coverage.
- **P2** — valuable extension after the core flow is proven.
- **Deferred** — intentionally postponed until evidence shows the need.

Sprint estimates below are deliberately coarse and should be refined during planning. Story Points (SP) use relative complexity: 1, 2, 3, 5, 8.

## Already delivered / baseline

The repository already includes the engineering operating model and CI quality gates; governed knowledge chunking, normalization/versioning, SQLite persistence, source connector boundary/reliability, deterministic parsing, ingestion orchestration, governed lexical retrieval, dense retrieval, hybrid retrieval, retrieval evaluations, knowledge tombstones, living architecture/learning documentation, Training structured extraction, grounded generation evaluation, and stable EvidenceRef-based artifact grounding.

Relevant merged PR sequence includes #1, #3, #5, #7-10, #12-17, #23-26, #29-34.

## Product architecture direction

```text
Tropos Core
├── governed knowledge
├── retrieval
├── evidence / provenance
├── persistence adapters
├── eval contracts
└── observability contracts

Resolve
├── knowledge article generation
├── case intake / classification
├── workflow selection
├── resolution retrieval
├── next best action
└── agent / self-service presentation

Training
└── approved operational knowledge → audience-specific training
```

## Sprint 1 — Grounded Knowledge Article MVP

**Sprint Goal:** Generate a fixed-format, evidence-backed Knowledge Article and measure its quality.

| ID | Priority | Story | SP | Dependencies |
|---|---|---|---:|---|
| RES-101 | P0 | Define canonical KnowledgeArticle domain model and templates | 5 | EvidenceRef |
| RES-102 | P0 | Define business intake and article-generation request contract | 3 | RES-101 |
| RES-103 | P0 | Generate grounded KnowledgeArticleDraft through provider-neutral port | 8 | RES-101, RES-102 |
| QE-101 | P0 | Define reusable eval dataset/run/score contracts | 5 | existing eval framework |
| QE-102 | P0 | Build Knowledge Article golden dataset and deterministic graders v1 | 8 | RES-103, QE-101 |

### Sprint 1 acceptance outcome

Given governed evidence and a typed article request, Tropos can create a troubleshooting/how-to/FAQ draft with stable EvidenceRefs, fixed structure, explicit gaps/conflicts, and an automated quality scorecard.

## Sprint 2 — Experimentation, regression and case classification

**Sprint Goal:** Compare candidate changes safely and turn raw cases into controlled resolution workflows.

| ID | Priority | Story | SP | Dependencies |
|---|---|---|---:|---|
| QE-103 | P0 | Build experiment runner and baseline-vs-candidate regression comparison | 8 | QE-101, QE-102 |
| OBS-101 | P1 | Add vendor-neutral trace/eval sink contracts and OpenTelemetry instrumentation boundary | 5 | QE-101 |
| OBS-102 | P1 | Add LangSmith adapter for experiments/traces without domain coupling | 5 | OBS-101, QE-103 |
| RES-104 | P0 | Define case taxonomy and CaseClassification contract | 5 | Resolve domain |
| RES-105 | P0 | Implement hybrid case classification: rules + structured model output | 8 | RES-104 |
| QE-104 | P0 | Build classification golden dataset and field/workflow graders | 5 | RES-104, RES-105 |

### Sprint 2 acceptance outcome

A candidate prompt/model/config can be compared against a baseline with regressions visible, and raw case text can be mapped into a validated classification/workflow contract with measurable accuracy.

## Sprint 3 — Resolve retrieval and Next Best Action

**Sprint Goal:** Turn classified cases into grounded, eligible recommendations.

| ID | Priority | Story | SP | Dependencies |
|---|---|---|---:|---|
| RES-106 | P0 | Build ResolutionRetrievalIntent and deterministic query builder | 5 | RES-104 |
| RES-107 | P0 | Retrieve workflow-specific governed evidence and measure Recall@K/MRR | 8 | RES-106 |
| RES-108 | P0 | Define RecommendedAction contract, eligibility and policy hooks | 5 | RES-104 |
| RES-109 | P0 | Generate/rank grounded candidate actions and escalation conditions | 8 | RES-107, RES-108 |
| QE-105 | P0 | Build NBA golden dataset and graders | 8 | RES-109 |
| QE-106 | P1 | Build end-to-end Resolve eval: case → classification → retrieval → NBA | 8 | QE-104, QE-105 |

## Sprint 4 — Production-like persistence and lifecycle

| ID | Priority | Story | SP | Dependencies |
|---|---|---|---:|---|
| PLAT-101 | P1 | Add Postgres repository adapters while retaining SQLite for local/test | 8 | repository ports |
| PLAT-102 | P1 | Provision Supabase staging and run shared repository contract tests | 5 | PLAT-101 |
| GOV-101 | P1 | Add Knowledge Article draft → review → approved/published lifecycle | 8 | RES-103 |
| GOV-102 | P1 | Capture generation provenance separately from content evidence | 5 | RES-103, QE-101 |
| QE-107 | P1 | Define release gates and CI/nightly/release eval cadence | 5 | QE-103, QE-106 |

## Sprint 5+ — Training and broader platform

| ID | Priority | Story | SP | Dependencies |
|---|---|---|---:|---|
| TRN-101 | P1 | Transform approved KnowledgeArticle into audience-specific TrainingDocument | 8 | GOV-101 |
| TRN-102 | P1 | Add training-specific golden dataset and evaluators | 5 | TRN-101 |
| API-101 | P1 | Expose Resolve capability APIs | 5 | RES-109 |
| UI-101 | P2 | Build agent/self-service Resolve UI | 8 | API-101 |
| UI-102 | P2 | Build Knowledge Article review/publish UI | 8 | GOV-101 |
| PLAT-103 | P2 | Add production deployment and operational dashboards | 8 | PLAT-102, OBS-102 |

## Delivery management and engineering performance

Delivery reporting is generated from repository data in [delivery-metrics.md](./delivery-metrics.md). The generated file is refreshed automatically by GitHub Actions on issue changes, merged pull requests, deployment-status changes, a daily schedule, or manual workflow dispatch.

The backlog document contains the operating rules; delivery-metrics.md contains the changing measurements. Planned values are not presented as actual delivery performance.

### Sprint control

**Scope management**
- Sprint scope is protected by default.
- New work is triaged as defect, compliance/regulatory need, urgent business need, or normal enhancement.
- Normal enhancements return to the product backlog for prioritization.
- In-sprint additions require an explicit accountable decision and one of three treatments: swap equivalent scope, explicitly increase sprint scope, or split to the smallest viable slice.
- Scope additions and removals remain visible in sprint reporting.

**Blocker management**
- A blocker is linked to the affected story and assigned an owner.
- Internal blockers are swarmed; external blockers are escalated through the dependency owner.
- Blocker age and impact on the Sprint Goal are reviewed during delivery cadence.
- If completion is no longer credible, the story is re-planned; unfinished points are not counted as velocity.
- Material blockers require root-cause and preventive-action capture where appropriate.

**Velocity**
- Velocity is accepted story points completed under the Definition of Done.
- Partial work does not earn partial velocity.
- Velocity is used for team-level capacity forecasting, not individual performance.
- After at least three completed sprints, rolling actual velocity may inform future commitment together with leave, dependencies, technical risk and Sprint Goal.

**Burndown**
- Burndown tracks remaining accepted sprint scope over time.
- An upward movement is valid when scope is explicitly added.
- Actual burndown is generated only when sprint dates are configured; no synthetic actuals are published.

### DORA metrics

Tropos tracks the four DORA software-delivery metrics separately from sprint metrics:

| Metric | Definition | Tropos measurement approach |
|---|---|---|
| Deployment frequency | How often changes reach production | Successful production deployments over the reporting window |
| Lead time for changes | Time from code change to production | Commit timestamp to production deployment timestamp |
| Change failure rate | Share of production changes that degrade service or require remediation | Production deployment linked to rollback, incident or explicit change-failure signal |
| Mean time to restore | Time to restore service after a production change failure | Incident/change-failure start to verified service restoration |

DORA data is reported only when the underlying production signals exist. Failed CI runs and failed pre-production deployment attempts are not classified as production change failures.

### Engineering-flow metrics

DORA is complemented by operational delivery measures such as PR cycle time, sprint remaining work, velocity, blocker age and scope change. These measures help diagnose flow; they are not substitutes for product quality or DORA outcomes.

### Automated reporting

The repository contains:

- `scripts/update_delivery_metrics.py` — computes repository-derived sprint, flow and available DORA metrics.
- `.github/workflows/delivery-metrics.yml` — refreshes the metrics surface automatically.
- `docs/product/delivery-metrics-config.json` — identifies the current sprint, sprint dates and production environment names.
- `docs/product/delivery-metrics.md` — generated reporting surface; it should not be edited manually.

Change failure rate and mean time to restore remain unavailable until production incident/change-failure signals are formally implemented. This is intentional; Tropos does not manufacture DORA values from unrelated repository events.

## Deferred until evidence justifies them

- ANN/HNSW migration or dedicated vector database
- heavy reranking pipelines beyond measured retrieval need
- LangGraph workflow orchestration before durable branching/HITL is required
- autonomous multi-agent orchestration
- full claim graph shared across capabilities
- direct provider coupling in domain/application layers
- replacing SQLite for local deterministic tests

## Jira-ready story template

Every implementation story should contain:

**User story**  
As a <persona/system role>, I want <capability>, so that <business outcome>.

**Business value**  
Why this matters and which risk/outcome it addresses.

**Scope**  
Explicit in-scope and out-of-scope boundaries.

**Acceptance criteria**  
Testable Given/When/Then or equivalent objective checks.

**Tasks**  
Architecture/domain work, implementation, automated tests/evals, documentation/evidence.

**Test strategy**  
Unit / contract / integration / AI eval / E2E requirements as applicable.

**Definition of Done**
- code and contracts merged
- CI green
- architecture/docs updated where impacted
- automated evidence captured
- no unsupported capability claims
- learning/decision record updated for meaningful trade-offs

## Quality engineering cadence

```text
Every PR
  formatting → lint → typing → unit → contract → fast integration → smoke eval

Nightly
  full development golden set → regression comparison → expensive judge evals → retrieval benchmark

Release candidate
  holdout set → E2E → security → performance → critical scenario gates

Production
  traces → runtime metrics → sampled online evals → failures harvested into regression dataset
```

## Backlog governance

1. P0 work must trace to the current product hypothesis or a release-blocking quality risk.
2. No new framework is introduced without an explicit problem, alternatives, downside and revisit trigger.
3. Each production defect should become a regression case when reproducible.
4. Golden cases are approved/versioned product specifications; synthetic LLM output is candidate data until validated.
5. Component evals diagnose failures; end-to-end evals determine product outcome quality.
6. Observability vendors remain adapters. Tropos owns correctness semantics, golden data and release gates.
7. New in-sprint scope requires explicit triage, estimate, owner and trade-off decision; it is never silently added.
8. Blocked work is visible, owned and escalated; unfinished points are never counted as completed velocity.
