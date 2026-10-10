# Tropos Archify visualizer

The Archify visualizer is the interactive architecture view for the current implemented Tropos platform.

## Permanent visualizer

After the repository's one-time GitHub Pages setting is enabled with **Source = GitHub Actions**, the live visualizer is available at:

https://kumarchandansingh.github.io/tropos/

The same platform page is also published at:

https://kumarchandansingh.github.io/tropos/architecture/

The code-derived Resolve implementation drill-down is published at:

https://kumarchandansingh.github.io/tropos/resolve/

The code-derived evaluation method and experiment-design view is published at:

https://kumarchandansingh.github.io/tropos/evaluation/

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

### One-time repository setting

GitHub Pages itself must be enabled once by a repository administrator:

`Settings → Pages → Build and deployment → Source → GitHub Actions`

The workflow intentionally does not attempt to create/enable the Pages site through the GitHub App because repository-admin permission is required for that operation. After this one-time setting, deployments are automatic.

## Source specification

- `candidate.json` — version-controlled Tropos platform dataflow specification.
- `resolve.json` — version-controlled Resolve architecture specification derived from current implementation evidence.
- `evaluation.json` — version-controlled evaluation product-quality map plus implemented experiment/comparison architecture.
- `tropos-platform.html` — generated platform viewer; not committed.
- `tropos-resolve.html` — generated Resolve implementation viewer; not committed.
- `tropos-evaluation.html` — generated evaluation method/design viewer; not committed.
- `.github/workflows/archify-pages.yml` — renders and publishes the live visualizer.
- `.github/workflows/archify-diagram-pilot.yml` — validates Archify changes on pull requests and uploads a review artifact.

The published workflow replaces the human-readable `main` revision in the spec with the exact deployed commit SHA before rendering. Source links in the live viewer therefore point to the code revision represented by that deployment.

## Current scope

The platform visualizer covers the implemented path from governed knowledge through retrieval and grounded AI:

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

### Resolve drill-down scope

The Resolve drill-down is authored from executable source on `main`, not from the roadmap. It currently shows:

- `ResolvedCase`, rule-based closure evidence evaluation, `EvaluateCaseClosure`, contract-only knowledge ports, and deterministic knowledge-action policy;
- typed Knowledge Article intake and system-owned generation policy;
- deterministic query/access orchestration through `KnowledgeChunkRetriever`;
- construction of evidence excerpts carrying stable `EvidenceRef`;
- provider-neutral `KnowledgeArticleGenerator` port and concrete LangChain adapter;
- structured output, temporary evidence aliases, exact alias resolution, and `KnowledgeArticleDraft`.

It explicitly marks unimplemented/classification/NBA/publish/UI work as absent rather than drawing roadmap components into the runtime topology.

### Evaluation drill-down scope

The evaluation drill-down has two intentionally different views:

- **Product quality map** — a conceptual map showing where software tests, invariant checks, retrieval benchmarks, model evals, and future product-outcome evaluation attach to the Tropos product flow.
- **Evaluation runtime** — the implemented experiment machinery: dataset/subject/provenance, `ExperimentRunner`, `EvalCaseExecutor`, observations/scores, persisted runs, baseline-versus-candidate comparison, uncertainty, and gates.

Conceptual nodes are explicitly tagged as quality-model concepts rather than implemented runtime components. Future agent/user outcome evaluation is shown only as a future quality boundary.

QE-108 through QE-111 remain outside the implemented runtime topology until they are delivered.

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
node .agents/skills/archify/bin/archify.mjs finalize architecture docs/diagrams/archify/resolve.json docs/diagrams/archify/tropos-resolve.html --repo-root . --quality showcase --json
node .agents/skills/archify/bin/archify.mjs finalize architecture docs/diagrams/archify/evaluation.json docs/diagrams/archify/tropos-evaluation.html --repo-root . --quality showcase --json
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
