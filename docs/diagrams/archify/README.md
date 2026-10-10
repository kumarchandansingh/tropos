# Tropos Archify visualizer

The Archify visualizer is the interactive architecture view for the current implemented Tropos platform.

## Permanent visualizer

After the GitHub Pages workflow is enabled and deployed, the live visualizer is available at:

https://kumarchandansingh.github.io/tropos/

The same page is also published at:

https://kumarchandansingh.github.io/tropos/architecture/

## Update model

The visualizer is regenerated automatically after relevant changes merge to `main`.

```text
relevant merge to main
        ↓
Live Archify Pages workflow
        ↓
inject exact deployed commit SHA
        ↓
Archify finalize / browser validation
        ↓
GitHub Pages deployment
        ↓
stable visualizer URL updated
```

Relevant triggers currently include:

- `apps/api/**`
- architecture documentation
- Tropos/Resolve/Training product docs
- Archify specifications/runtime
- the Pages workflow itself

This is continuous publication after repository changes; it is not a runtime reflection of unmerged branches.

## Source specification

- `candidate.json` — version-controlled Tropos architecture dataflow specification.
- `tropos-platform.html` — generated self-contained interactive viewer; not committed.
- `.github/workflows/archify-pages.yml` — renders and publishes the live visualizer.
- `.github/workflows/archify-diagram-pilot.yml` — validates Archify changes on pull requests and uploads a review artifact.

The published workflow replaces the human-readable `main` revision in the spec with the exact deployed commit SHA before rendering. Source links in the live viewer therefore point to the code revision represented by that deployment.

## Current scope

The visualizer currently covers the implemented path from governed knowledge through retrieval and grounded AI:

- source capture and governed ingestion;
- SQLite canonical/version/chunk/embedding/run state;
- BM25 lexical retrieval;
- exact dense retrieval;
- RRF hybrid retrieval;
- stable `EvidenceRef`;
- Resolve Knowledge Article generation;
- Training procedure generation;
- evaluation contracts/regression;
- CI quality gates.

Planned capabilities are not shown as implemented nodes.

## Guided views

Use the guided views to focus on:

- **Knowledge foundation**
- **Retrieval**
- **Resolve**
- **Training**
- **Evaluation**

Each node links to source-backed repository evidence.

## Render locally

Node.js >=18, Git and Chrome/Chromium are required for all `finalize` gates.

```sh
export ARCHIFY_UPDATE_CHECK_DISABLED=1
node .agents/skills/archify/bin/archify.mjs doctor
node .agents/skills/archify/bin/archify.mjs finalize dataflow docs/diagrams/archify/candidate.json docs/diagrams/archify/tropos-platform.html --repo-root . --quality showcase --json
```

The `finalize` command performs schema validation, delivery/integrity checks and real-browser checks.

## Security boundary

- Archify is vendored under `.agents/skills/archify` and updated only through repository review.
- Rendering workflows use credential-free checkout for the renderer.
- GitHub Pages deployment uses only `pages: write` and `id-token: write` in the publishing workflow.
- External fork PRs do not execute the vendored JavaScript pilot.
- The GitHub-hosted runner is not network-isolated and the vendored JavaScript is not treated as a fully audited dependency.

## Documentation rule

The visualizer is a source-backed architecture view, not the sole documentation source. Material architecture changes must update the living architecture/ADR/product documentation as required; the viewer should then be updated in the same delivery slice when its represented topology changes.
