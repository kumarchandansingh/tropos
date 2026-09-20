# ADR-001: Modular monolith with Ports-and-Adapters boundaries

**Status:** Accepted  
**Date:** 2026-09-20

## Context

Tropos is early-stage but already contains responsibilities that will evolve at different rates: business decision policy, ingestion, retrieval, persistence, source connectors, AI/model integrations and delivery interfaces.

The system needs enough separation to prevent infrastructure choices from becoming business policy, without paying the operational cost of distributed services before there is evidence that independent deployment or scaling is required.

## Options considered

### 1. Script/application with direct infrastructure dependencies

Fastest initially, but database/search/model SDK types would likely leak into business logic and make later replacement expensive.

### 2. Microservices from the start

Strong deployment boundaries, but premature for the current product maturity. It would introduce networking, deployment, tracing, failure handling and distributed-data concerns before Tropos has an end-to-end hosted workload.

### 3. Modular monolith with Ports-and-Adapters

Keep one deployable codebase while separating domain policy, application orchestration, contracts and replaceable implementations.

## Decision

Tropos will start as a **modular monolith** using **Ports-and-Adapters / Hexagonal architecture**.

- domain owns business concepts and invariants;
- application owns use-case orchestration and replaceable boundary contracts;
- adapters implement algorithms or infrastructure integrations;
- presentation and bootstrap/composition remain outward layers when introduced;
- infrastructure must not define the domain model.

## Rationale

This provides an explicit dependency rule without forcing operational distribution. Retrieval, persistence and model technologies can change behind ports while the product decision vocabulary remains stable.

## Consequences

### Positive

- domain/application behavior can be unit-tested without infrastructure;
- retrieval and persistence technologies remain replaceable;
- future AI providers can be integrated without making SDK output the domain contract;
- service extraction remains possible later if independent deployment becomes justified;
- early development remains operationally simple.

### Negative / trade-offs

- more interfaces/files than a direct script;
- developers must understand responsibility boundaries;
- incorrect “port for everything” design could add needless abstraction;
- deployment isolation between modules does not exist today.

## Evidence

Current code follows the decision through:

- `apps/api/src/tropos/domain/`
- `apps/api/src/tropos/application/evaluate_case_closure.py`
- `apps/api/src/tropos/application/ports/`
- `apps/api/src/tropos/adapters/`

`EvaluateCaseClosure` depends on Protocol-based ports for retrieval, coverage evaluation and decision storage rather than concrete infrastructure implementations.

## Revisit when

Reconsider the modular-monolith deployment boundary when one or more modules have demonstrated a real need for:

- independent scaling;
- independent release cadence;
- isolation for security/reliability reasons;
- a distinct ownership boundary;
- runtime characteristics that materially conflict with the rest of the application.

Until then, preserve modular boundaries inside one deployable system.
