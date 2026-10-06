# Learning: a test plan is not a test result

Authoritative behavior: [Saved evaluation architecture](../architecture/EVALUATION_RUNS.md).
Decision: [ADR-012](../decisions/ADR-012-versioned-evaluation-catalogues-and-saved-runs.md).

## Failure and invariant

An average can improve when the hardest cases silently fail to execute. A dashboard can also present an old result against newly edited labels. The invariant is that each reported result points to the exact definition, fixture state and configuration that produced it; missing or invalid observations remain visible.

## Concepts

An expectation is an input to evaluation. An observation is what the retriever actually returned. An assertion compares evidence with an expectation or invariant. A run outcome summarizes those assertions without overwriting them. Execution completion and quality success are different facts.

Content-addressed snapshots freeze inputs. Business IDs/version labels keep them readable. Both are needed: a version label alone can be reused accidentally, while a hash alone does not explain the business scenario.

## Alternatives, decision and cost

Print-only test output is cheap but ephemeral. Mutable report documents are easy to edit but can detach results from inputs. Tropos uses immutable dataset registrations and append-only relational evidence in SQLite. This adds schema/lifecycle complexity and local storage; it does not create a compliance-grade ledger.

Isolated per-case ingestion costs execution time but prevents one access-revocation scenario from corrupting another case's corpus. We will revisit this when measured run cost warrants reusable snapshots or worker processes.

## Evidence

The standalone Windows command exposed a resource-lifecycle bug: SQLite's connection context commits or rolls back a transaction but does not close the connection. Temporary fixture cleanup could therefore fail after an otherwise completed run. Both ingestion and retrieval adapters now close connections explicitly after transaction completion, including exception paths. The command regression disables garbage collection and verifies saved results plus immediate temporary-directory cleanup, preventing success that depends on incidental collection timing.

`test_saved_runs.py` covers changed-definition rejection, lifecycle scenarios, unauthorized/old/forged returned evidence, error continuation, interruption, terminal-state protection and read-only reporting. The unchanged V1 test preserves the earlier lexical baseline. V2 records 15 expected BM25 passes, two semantic misses and one unexecuted draft; honest failure data is the input to the future vector comparison.

## Interview probes

- Why can a completed run fail? All queries can execute successfully while returning the wrong evidence.
- Why is a missing result not always a no-answer pass? A backend error is absence of observation, not successful abstention.
- Why exclude invalid observations from relevance metrics? A score computed from unauthorized or fabricated evidence is not a valid quality measurement. The invalid case still blocks the outcome.
- Why not trust the returned access policy? A broken adapter could attach an incorrect policy; the evaluator checks authoritative fixture state separately.
- Why keep draft cases visible? They expose planned coverage without pretending it has been tested.

## Scale and release implications

Synthetic cases catch regressions but cannot establish enterprise accuracy. Held-out representative datasets, reviewed labels, model/configuration versions and latency measurements are required before release claims. A business visualizer should render these records and their limitations, not introduce a second scoring implementation.
