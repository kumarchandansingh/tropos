# Evaluation strategy

Software correctness, filesystem integration, document quality, and product outcomes are separate concerns.

## Software and integration

Required gates: Ruff formatting and lint, mypy, standard-library unittest suite, package build, JavaScript syntax check. GitHub Actions runs the Python gates on Windows and Ubuntu.

Synthetic cases cover differently named identical files, same-sized different files, retained-copy rules, unknown selections, document-only matches, stale extras and keepers, links, hard links, cancellation, persisted quarantine manifests, one-shot execution, restore conflicts, raw/document identity separation, and local HTTP authorization.

Desktop browser validation must exercise scan → selection → plan → quarantine → restore with synthetic folders. Never use real personal files for automated destructive-flow tests.

## Document quality

The revision discovery threshold is provisional. Before expanding document recommendations, curate a versioned corpus with exact copies, text-equal layout changes, resume targeting changes, scanned PDFs, signatures, forms and malformed documents. Measure candidate precision/recall separately from user decisions. No document similarity result may cross the exact-only action boundary.

## Remaining release limitations

OS-enforced parser memory limits, stronger handle-based moves, automated crash reconciliation, cross-volume integration on a physical second drive, large-folder benchmarks, accessibility audits, signed installation and updates remain planned. A passing unit suite does not establish these properties.
