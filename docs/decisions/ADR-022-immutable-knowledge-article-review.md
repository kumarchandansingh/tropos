# ADR-022 — Immutable local review snapshots before authenticated article publication

Status: Accepted for GOV-101A local foundation (not production authorization)

## Context

Tropos can generate evidence-backed `KnowledgeArticleDraft` objects, but a
draft has no independent review decision, durable history, or invariant
preventing its content from changing between review and downstream use.
Implementing a web approval button without those invariants would produce a
misleading workflow and invite later rework.

## Decision

- Save the full canonical JSON of each submitted `KnowledgeArticleDraft`,
  including every stable `EvidenceRef`, in a separate SQLite review store.
- Bind the review to SHA-256 of that immutable JSON; never silently overwrite
  an article ID. A future revision needs its own revision identity.
- Maintain explicit `IN_REVIEW`, `APPROVED`, `CHANGES_REQUESTED` states.
  Approval is **not** publication.
- Make reviewer decisions atomic with append-only decision events and a
  compare-and-swap version check.
- Reject self-review at this local boundary, but treat caller-supplied actor IDs
  as unverified until an authenticated, tenant-aware API exists.
- Keep the existing generated `KnowledgeArticleDraft` contract unchanged and
  avoid introducing LangGraph or an LLM into deterministic review decisions.

## Alternatives

1. **Add a UI action only.** Rejected: no protected identity of reviewed content
   and no durable decision trail.
2. **Mutate the original draft in place.** Rejected: would make historic approval
   point to potentially different evidence-backed text.
3. **Add an enterprise workflow framework now.** Deferred: this bounded state
   transition does not require a workflow engine.
4. **Introduce Postgres immediately.** Deferred: SQLite is already the local
   baseline and permits contract development without remote infrastructure.

## Consequences and limitations

The first slice supports one immutable submission and one terminal review
decision per article ID. It does not offer authenticated reviewer identity,
tenant scoping, permissioned review queues, resubmission of revised drafts,
publication, push notifications or a browser review interface. The SQLite
record and its hash are integrity checks, not signatures or an adversarial
tamper-proof ledger: an actor with database write access could alter both.

## Revisit trigger

Introduce verified identities, tenant-aware access controls and a revision
aggregate before exposing this to remote users. Evaluate a workflow engine
only when retries, waiting approvals, timeouts, escalations or multiple
nonterminal transitions create complexity that the current deterministic
state model cannot manage.
