# Tropos Archify ingestion pilot

A source-backed documentation pilot for the synchronous ingestion path at Tropos revision `8cbad1f6261bb11f16a40cfe7f77a1887d29e5ab`. The diagram illustrates checked code and does not assert production deployment.

## What to open

- `candidate.json` — version-controlled Archify dataflow specification, including source-code locations, explanation cards, and guided views.
- `tropos-ingestion.html` — **generated** self-contained interactive diagram. Download the `tropos-archify-ingestion` artifact from the `Archify diagram pilot` GitHub Actions run. It is not committed.
- `docs/architecture/INGESTION_NORMALIZATION.md` — source explanation of identity, normalization, governance, and versioning.

## Learning and review in the viewer

Use the four guided views — **Source evidence**, **Content versioning**, **Access governance**, and **Persistence and replay** — to explore the implemented components. The explanation cards cover source provenance, canonical version decisions, independent access updates, and durable run history. Open each node's linked source references to verify the claims.

Keep the diagram itself compact; put detailed examples and trade-offs in cards or linked architecture documentation. Every description must be grounded in implementation or explicitly labeled planned/unknown. Do not add invented APIs, cloud services or LLM calls.

## Render locally

Node.js >=18, Git and Chrome/Chromium are required to run all `finalize` gates.

```sh
export ARCHIFY_UPDATE_CHECK_DISABLED=1
node .agents/skills/archify/bin/archify.mjs doctor
node .agents/skills/archify/bin/archify.mjs finalize dataflow docs/diagrams/archify/candidate.json docs/diagrams/archify/tropos-ingestion.html --repo-root . --quality showcase --json
```

The `finalize` command runs validation, delivery, integrity checks and real-browser checks. A valid JSON specification is not sufficient evidence of success.

## Security boundaries

- Archify v3.0.1 is vendored under `.agents/skills/archify` and updated only after review.
- The workflow uses read-only permissions, a credential-free checkout, commit-SHA-pinned GitHub Actions, and disables Archify's optional update check.
- Execution of the vendored JavaScript in this workflow is limited to manual dispatch or same-repository pull requests; external fork PRs are skipped.
- GitHub Actions artifacts expire after seven days; review their contents before external distribution.
- These controls reduce credential and fork exposure; the GitHub-hosted runner is **not network-isolated**, and the vendored JavaScript is **not a fully audited dependency**.

## Correctness boundaries

- Replayed completed captures return a prior result without new ingestion.
- `NO_CONTENT_VERSION` creates no document or chunks; `REBASELINE_REQUIRED` needs explicit review.
- Access policy can refresh independently even if content is unchanged. Combined access+content changes refresh governance first.
- External enterprise connectors, hosted presentation and model-assisted parsing are **not represented as implemented**.
- Recheck source references after code changes. Do not merge until `finalize` and the existing repository CI pass and the HTML is visually reviewed.
