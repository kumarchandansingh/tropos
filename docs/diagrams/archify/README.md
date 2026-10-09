# Tropos Archify ingestion pilot

This is a **documentation-only pilot**. The proposed dataflow is grounded in the ingestion code at `8cbad1f6261bb11f16a40cfe7f77a1887d29e5ab` (the `main` revision inspected during authoring). It is **not** proof of current deployment or of any future architecture.

## Source and generated output

- `candidate.json`: typed Archify Data Flow specification; contains repository-relative source line references.
- `tropos-ingestion.html`: **generated**, offline-viewable diagram. This file is produced by the validation workflow and uploaded as a workflow artifact; it is not yet committed.
- `docs/architecture/INGESTION_NORMALIZATION.md`: existing detailed design and identity/versioning rules.

## Render locally

Run from the repository root with Node.js >=18 installed:

```sh
export ARCHIFY_UPDATE_CHECK_DISABLED=1
node .agents/skills/archify/bin/archify.mjs doctor
node .agents/skills/archify/bin/archify.mjs finalize dataflow docs/diagrams/archify/candidate.json docs/diagrams/archify/tropos-ingestion.html --repo-root . --quality showcase --json
```

The `finalize` command performs validation, delivery, strict checks, and browser checks; it can fail if Chrome/Chromium is unavailable. A schema-shaped source specification is *not* a substitute for a passing finalize receipt.

The `Archify diagram pilot` GitHub Actions workflow renders and tests this diagram in an isolated runner and uploads the HTML plus receipts. No existing Tropos application or CI logic is modified.

## Important nuances

- `NO_CONTENT_VERSION` does not create chunks.
- `REBASELINE_REQUIRED` is a deliberate hold, not automatic reprocessing.
- If the access policy changes concurrently with content, governance may refresh before creating the new version.
- Replayed completed captures return prior results, and run records capture stage and outcome.
- This visual represents the synchronous ingestion path. SharePoint, Gmail, Jira connectors, hosted presentation layers, and model-assisted parsing are not shown as implemented.

## Maintainability

Recheck cited paths/lines after code changes. Re-generate this HTML after editing `candidate.json`. Keep generated receipts out of application/runtime paths. Do not merge until the workflow's Archify `finalize` stage is verified as passing.
