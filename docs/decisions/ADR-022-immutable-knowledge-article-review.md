# ADR-022 — Immutable local review snapshots before authenticated article publication

Status: Accepted for GOV-101A local foundation (not production authorization)

## Context

Tropos can generate evidence-backed `KnowledgeArticleDraft` objects, but a
draft has no independent review decision, durable history, or invariant
preventing its content from changing between review and downstream use.
Implementing a web approval button without those invariants would produce a
misleading workflow and invite later rework.

## Decision drivers and constraints

- Approved content must not be silently replaced.
- Review status changes must be atomic and recoverable after process restart.
- Scope must remain locally testable without identity infrastructure or an LLM.
- Never equate approval with publication.

## Decision

- Save the full canonical JSON of each submitted `KnowledgeArticleDraft`,
  including every stable `EvidenceRef`, in a separate SQLite review store.
- Bind the review to SHA-256 of immutable JSON and identify a reviewed revision
  by the compound key `(tenant_id, article_id, revision_no)`. Every content edit
  creates a new numbered revision without overwriting prior approvals.
- Maintain explicit `DRAFT` (transactional submission), `IN_REVIEW`,
  `APPROVED`, `CHANGES_REQUESTED` states.
  Approval is **not** publication.
- Make reviewer decisions atomic with append-only decision events and an
  expected last-event-sequence check on an exact revision.
- Align logical IDs and event/claim citation tables with proposed DATA-101
  (PR #118); preserve full `EvidenceRef` values within frozen article JSON.
- Reject self-review at this local boundary, but treat caller-supplied actor IDs
  as unverified until an authenticated, tenant-aware API exists.
- Keep the existing generated `KnowledgeArticleDraft` contract unchanged and
  avoid introducing LangGraph or an LLM into deterministic review decisions.

## Options considered

1. **Add a UI action only.** Rejected: no protected identity of reviewed content
   and no durable decision trail.
2. **Mutate the original draft in place.** Rejected: would make historic approval
   point to potentially different evidence-backed text.
3. **Add an enterprise workflow framework now.** Deferred: this bounded state
   transition does not require a workflow engine.
4. **Introduce Postgres immediately.** Deferred: SQLite is already the local
   baseline and permits contract development without remote infrastructure.

## Consequences and limitations

Each article can contain numbered immutable revisions. Review events and
claim-indexed evidence references are scoped to the tenant, article and exact
revision; after a terminal review, a caller may submit a *new* revision using
the expected prior revision number. The earlier approval does not carry over.
This resolves the identity conflict with DATA-101's target conceptual model.

The tables implement a **local subset** of the proposed production model:
`tenants`, `knowledge_articles`, `article_revisions`, `article_citations`
and `review_events`. Full principal foreign keys, governed evidence-set/chunk
references, user roles and publication tables are not implemented here.
Caller-provided tenant and actor IDs are unverified. There is no hosted
authorization, review UI, publication or notification workflow. The review
hash detects ordinary content alteration but is not a cryptographic signature
against privileged database attackers.

A prior unscoped `article_reviews` database is deliberately rejected rather
than silently reinterpreting historical approvals under a fabricated tenant.
A verified tenant assignment and explicit backfill are needed if such data
must be migrated. DATA-101 is not a production migration or a dependency
on merging PR #118.

## Evidence

- `apps/api/src/tropos/core/domain/article_review.py` canonical article snapshot and status contracts.
- `apps/api/src/tropos/core/adapters/persistence/sqlite_article_review.py` SQLite transactional store.
- `apps/api/tests/unit/core/adapters/persistence/test_sqlite_article_review.py` synthetic, deterministic regression tests.

## Revisit when

Introduce verified identities, tenant-aware access controls, evidence/source
foreign keys and publication eligibility before exposing this to remote users. Evaluate a workflow engine
only when retries, waiting approvals, timeouts, escalations or multiple
nonterminal transitions create complexity that the current deterministic
state model cannot manage.
