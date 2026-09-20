# ADR-001: Modular monolith with Ports-and-Adapters boundaries

**Status:** Accepted  
**Date:** 2026-09-20

## Context

Tropos contains business policy, ingestion, retrieval contracts, evidence models, and infrastructure concerns that will evolve at different rates. The code needs clear dependency boundaries without introducing distributed-system overhead before independent deployment or scaling is required.

## Options considered

### Direct application with infrastructure dependencies

Lowest initial ceremony, but persistence, search, or model SDK types can leak into business logic and make replacement expensive.

### Microservices from the start

Provides deployment isolation, but adds networking, deployment, tracing, failure handling, and distributed-data concerns before Tropos has an end-to-end hosted workload.

### Modular monolith with Ports-and-Adapters

Keep one deployable codebase while separating domain policy, application orchestration, contracts, and replaceable implementations.

## Decision

Tropos uses a **modular monolith** with **Ports-and-Adapters / Hexagonal architecture**.

- Domain modules own business concepts and invariants.
- Application modules own use-case orchestration and boundary contracts.
- Adapters implement deterministic algorithms and external integrations.
- Presentation and composition remain outer layers when introduced.
- Infrastructure types do not define the domain model.

Reusable governed-knowledge behavior lives under `tropos.core`. Capability-specific behavior lives under `tropos.capabilities`.

## Consequences

### Positive

- Domain and application behavior can be tested without infrastructure.
- Persistence, retrieval, and model providers remain replaceable.
- Capability policy stays separate from reusable evidence mechanics.
- Service extraction remains possible if operational requirements justify it later.

### Negative / trade-offs

- The codebase contains more explicit contracts than a direct script.
- Module boundaries require discipline to avoid unnecessary abstractions or dependency leakage.
- Modules share one deployment boundary today.

## Evidence

Current module boundaries are visible in:

- `apps/api/src/tropos/core/domain/`
- `apps/api/src/tropos/core/application/`
- `apps/api/src/tropos/core/adapters/`
- `apps/api/src/tropos/capabilities/resolve/domain/`
- `apps/api/src/tropos/capabilities/resolve/application/`
- `apps/api/src/tropos/capabilities/resolve/adapters/`

`EvaluateCaseClosure` depends on retrieval, coverage, and decision-store contracts rather than concrete infrastructure implementations.

## Revisit when

Reconsider the deployment boundary when a module demonstrates a need for independent scaling, release cadence, ownership, security/reliability isolation, or runtime characteristics that conflict materially with the rest of the application.
