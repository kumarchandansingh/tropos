# Saved retrieval evaluation

Implemented: a validated synthetic catalogue, isolated scenario execution, SQLite run persistence and JSON/Markdown export. This is the foundation for the later business visualizer. Embeddings, vector/hybrid search and the interactive dashboard remain planned.

## Definition and observation boundaries

`Catalogue` validates schema 2, source fixtures, case ownership/purpose, draft or approved status, rank expectations, tenant/group contexts and scenario updates. `catalogue_v2.json` preserves the 14 V1 scenarios and adds an exact policy identifier, current-version retrieval, access revocation and a draft deletion scenario. V1 and its regression test remain unchanged. Labels remain knowledge-level; duplicate chunks of one knowledge item count once within the first five returned chunks.

Dataset ID plus version cannot be reused with changed contents in one evaluation store. Canonical JSON SHA-256 identifies the full snapshot, including expectations, approval state and scenario updates. A separate digest identifies the base corpus. The current catalogue is development data, not held-out evidence. The format accepts a holdout split, but the repository does not supply a holdout set or enforce organizational approval identity.

`execute_catalogue` depends on a scenario-context factory and the existing `KnowledgeChunkRetriever` port. The concrete fixture composition ingests the base documents into a new temporary SQLite database for each case, then applies that case's ordered source updates. This exercises real ingestion, governance refresh, versioning and BM25. It cannot mutate a user's knowledge database. Frozen fixture capture timestamps remove irrelevant timestamp churn.

The fixture adapter separately reads current persisted chunks to construct the evaluation oracle. Assertions compare returned chunks against that authoritative snapshot, including access policy and exact evidence fields. Unknown, historical, unauthorized or modified returned evidence is redacted in stored hits and blocks the case. This oracle reads persisted state, so it is not an independent proof that ingestion itself is correct; ingestion retains separate regression tests.

## Relational model

| Table | Identity / purpose |
| --- | --- |
| eval_datasets | Digest PK; unique dataset ID/version; immutable full definition and corpus digest |
| eval_cases | Dataset digest + case ID; immutable exact case definition |
| eval_runs | Run ID; dataset FK; provenance, timestamps and execution lifecycle |
| eval_executions | Run ID + case ID; state, duration, safe error class |
| eval_hits | Execution FK + position; ranked actual evidence or redaction marker |
| eval_assertions | Execution FK + assertion name; pass/fail and rule explanation |
| eval_metrics | Execution FK; versioned bounded metric payload |

Schema version 1 uses a dedicated evaluation database and foreign keys. Definitions and result detail tables reject updates/deletes through triggers. Store methods reject overwriting terminal executions or appending through the public API after run closure. This is local auditability, not a tamper-proof compliance ledger; an administrator controlling the SQLite file can replace it.

Case states: not_run -> running -> passed / failed / error. Draft cases remain not_run. Run states: running -> completed / interrupted. `completed` describes execution finishing, not quality success. The derived outcome is failed for any failed/error case, incomplete for missing observations or unfinished runs, and passed only when every catalogue case completed successfully. Draft cases prevent an all-passed catalogue claim.

Every case completion commits its state, hits, assertions and metrics together. Caught execution errors record only their exception class to avoid echoing backend payloads. An orderly interrupt closes the run as interrupted; a killed process can leave it running. Report generation shows that incomplete state. Automatic resume, worker coordination, cancellation UI and recovery of killed runs are planned.

## Metrics and release interpretation

JSON reports include case metrics and aggregates with case counts. Answerable cases use Recall@1/3/5, Precision@5 and reciprocal rank; expected-empty cases use no-answer correctness. Precision uses a fixed denominator of five, preserving V1 semantics. Mean reciprocal rank appears as the aggregate reciprocal_rank value. An empty metric population yields null, not zero or a pass.

Errored/not-run cases do not contribute to quality means and remain in visible counts. Results violating access/currentness/integrity/shape invariants are excluded from quality means as invalid observations, while their failed status remains blocking. Reports disclose excluded cases. No metric is a probability of answer correctness. This release does not generate answers.

Run provenance records code revision, dirty-working-tree flag, dependency lock digest, Python version, retrieval and evaluator versions, chunk size, cutoff and named gate policy. A dirty run is exploratory; commit the code before collecting a release comparison. Mutable model/provider configuration is outside this release.

## Commands

From `apps/api` after `uv sync --dev --locked`:

```sh
uv run python -m tropos.evals catalogue --dataset evals/retrieval/catalogue_v2.json --format markdown --output planned-tests.md
uv run python -m tropos.evals run --dataset evals/retrieval/catalogue_v2.json --lockfile uv.lock --database evaluation-runs.sqlite --output run.json
uv run python -m tropos.evals report --database evaluation-runs.sqlite --run-id RUN_ID --format markdown --output results.md
```

The run prints its ID to stderr. Exit codes: 0 all cases passed; 1 saved failed/incomplete outcome; 2 input/setup error. The reference BM25 run intentionally exits 1 because the two semantic-gap cases remain misses and the deletion scenario is draft. CI tests assert that truthful baseline rather than requiring a fabricated passing evaluation.

Viewing or exporting a report never reruns retrieval or invokes a model. Markdown exports show planned purpose, expected IDs, actual ranked titles, source version, excerpts and individual checks. Reports are synthetic-only local artifacts. Hosted viewer authorization and a business dashboard are future work.

## Next boundary

Add embedding configuration/cache/jobs behind independent ports, then a governed vector retriever. Reuse this evaluation contract and add calibrated no-answer behavior and comparable configuration snapshots. Build the interactive visualizer after saved observations and vector comparisons exist. Versioned human review, chunk-level labels, held-out approval workflows and category comparison views remain planned.
