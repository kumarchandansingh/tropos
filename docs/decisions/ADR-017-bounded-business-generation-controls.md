# ADR-017: bounded business generation controls and system-owned governance

**Status:** Accepted  
**Date:** 2026-10-10

## Context

Business users need limited control over generated Knowledge Articles, but allowing arbitrary prompt editing would mix user preferences with security, evidence, conflict handling, and product-policy rules. That would make quality regression testing and governance difficult.

## Options considered

1. Expose the complete system prompt to business users.
2. Allow no business control and hard-code all generation behavior.
3. Expose typed, bounded business inputs while keeping governance rules system-owned and versioned.

## Decision

Use a typed `KnowledgeArticleGenerationRequest` for business intent and a separate system-owned generation policy.

Business-editable fields include:

- subject/problem;
- article type;
- product/module;
- bounded context;
- explicit retrieval keywords;
- detail level;
- focus areas;
- preferred terminology.

Business input cannot override:

- authorization;
- requirement for evidence;
- fixed article structure;
- conflict/missing-information handling;
- unsupported-claim policy.

Prompt-profile identity/version is system-selected so generation behavior can be tied to evaluation runs later.

## Why

This preserves useful configurability without turning prompts into an uncontrolled policy surface. Typed inputs can be validated, versioned and regression-tested.

## Consequences

### Positive

- business intent is explicit and testable;
- governance remains consistent across users;
- prompt changes can later be versioned/evaluated independently of business input;
- retrieval and generation inputs can be inspected before a model call.

### Negative / trade-offs

- advanced users cannot arbitrarily change article layout/tone/system behavior;
- new supported preferences require schema/product work;
- a future prompt-administration product will require lifecycle, approval and eval controls.

## Evidence

- PR #65: bounded Knowledge Article intake
- `tropos.capabilities.resolve.application.knowledge_article_request`
- `docs/architecture/KNOWLEDGE_ARTICLE.md`

## Revisit when

A controlled prompt/template administration feature is required with explicit permissions, versioning, approval, regression testing and rollback.
