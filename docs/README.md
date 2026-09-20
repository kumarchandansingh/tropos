# Tropos documentation

Tropos documentation is organized by purpose so architecture, reference material, delivery guidance, and decision history do not compete on the same page.

## Product and architecture

| Document | Purpose |
| --- | --- |
| [Product model](product/PRODUCT_MODEL.md) | Problem, users, decision outcomes, and product boundaries |
| [Architecture overview](architecture/ARCHITECTURE_OVERVIEW.md) | Module boundaries, dependency direction, and system responsibilities |
| [Ingestion and normalization](architecture/INGESTION_NORMALIZATION.md) | Raw capture, canonicalization, version resolution, and governance refresh |
| [Knowledge model](architecture/KNOWLEDGE_MODEL.md) | Evidence entities, identity layers, provenance, access, and chunk semantics |
| [RAG architecture](architecture/RAG_ARCHITECTURE.md) | Implemented RAG foundation and target retrieval/decision pipeline |

## Engineering reference

| Document | Purpose |
| --- | --- |
| [Codebase map](architecture/CODEBASE_MAP.md) | Source layout and module ownership |
| [Evaluation strategy](quality/EVAL_STRATEGY.md) | Software, retrieval, AI, and product-quality evaluation |
| [CI/CD](delivery/CI_CD.md) | Pull-request integration, quality gates, and deployment boundary |
| [Environment strategy](delivery/ENVIRONMENT_STRATEGY.md) | Runtime-environment model and future promotion path |

## Architecture decisions

[Architecture Decision Records](decisions/README.md) preserve the context and trade-offs behind durable choices. Living architecture documents describe the system as it exists; ADRs explain why important choices were made.

## Status terms

Architecture documents use these terms only when a capability boundary needs to be explicit:

| Status | Meaning |
| --- | --- |
| **Implemented** | Executable behavior exists in the repository. |
| **Contract only** | An interface or domain contract exists without a production adapter. |
| **Planned** | Intended work with no executable implementation yet. |
| **Deferred** | Intentionally postponed until requirements or evaluation justify it. |

## Suggested reading paths

**Understand the product:** Product model → Architecture overview → Knowledge model.

**Understand ingestion and retrieval:** Ingestion and normalization → Knowledge model → RAG architecture → Evaluation strategy.

**Understand the repository:** Codebase map → CI/CD → Architecture decisions.
