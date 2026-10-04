# Katharo

**Make room. Keep what matters.**

Katharo is a Windows-first local file review app. It finds exact duplicates, distinguishes document comparison from file equality, and moves approved extras into a reversible quarantine.

Its interface uses the visual principles of Apple's website: generous spacing, strong typography, neutral surfaces, and restrained blue controls. Katharo has no affiliation with Apple and includes no Apple logos, imagery, or proprietary fonts.

## Run

Requires Python 3.12 or newer. From this repository:

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\katharo
```

The application opens at http://127.0.0.1:8765. It runs locally; do not expose this development server to a network. On another OS the core and browser UI work, but Windows is the intended initial platform.

Alternatively, from an environment with pypdf already installed:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m katharo.server
```

Choose a personal folder, scan, select exact extra copies, review the retained copies, enter a separate quarantine folder, validate the plan, and explicitly confirm. Review per-file outcomes in Quarantine history. Restore refuses to overwrite occupied original locations.

## Implemented

- Native folder picker and editable folder paths; optional subfolders.
- Background scan with progress, cancellation, skipped-file reporting, type analytics.
- Size filtering and streamed SHA-256 matching; fresh hashes and byte equality before quarantine.
- Hard-link alias exclusion, link/junction exclusion, system-folder restrictions, cloud-placeholder skipping.
- Deterministic PDF, DOCX, TXT and Markdown extraction in separate time-bounded processes.
- Matching normalized text and word-shingle revision candidates; extracted text comparison and keep-both decisions.
- Document groups are review-only; only exact duplicates enter cleanup plans.
- SQLite scan, decision and action records; quarantine manifests; per-item failures and restore.
- Local session token, origin and Host checks; no remote resources or document uploads.

## Boundaries and limitations

This is an initial local release, not an enterprise endpoint agent. Do not use it to clean system/application folders or records governed by organizational retention rules.

Same-drive quarantine does **not** free space. Cross-drive transfer frees source-drive space only after a verified destination copy and source removal. Total storage remains occupied until the user separately disposes of quarantine. Katharo exposes no permanent-delete action.

Document extraction is limited to 30 MB, 200 PDF pages, 2 million text characters, and 300 distinct document candidates per scan. OCR, visual PDF comparison, highlighted text diffs, automatic categorization, portable inventory export, USN incremental scanning, and learned cross-scan keeper preferences are planned.

The parser process has a time limit but no OS-enforced memory sandbox. Similarity is a word-overlap score, not an equivalence probability. Extracted equality can omit formatting, images, signatures, annotations, and document purpose.

Filesystem operations are not atomic with SQLite commits. A crash can leave an item in `moving` or `restoring`; use its manifest and history to reconcile. Restore supports available quarantine items but does not overwrite existing originals. Failed partial copies are retained for manual review. A competing process can still change a file between revalidation and a move; this initial release does not claim adversarial race resistance or guaranteed recovery.

## Quality checks

```powershell
python -m ruff format --check src tests
python -m ruff check src tests
python -m mypy src tests
python -m unittest discover -s tests -v
python -m build
node --check src/katharo/web/app.js
```

Tests use synthetic files. No real resumes, personal inventories, extracted content, credentials, or quarantine manifests belong in this repository.

Start with [documentation](docs/README.md).


Batch review excludes Office `~$` owner records. Exact groups appear collapsed, largest recoverable bytes first. A single selection action proposes extras for groups sharing the same extension, retaining the suggested keeper (unnumbered name, then shortest path). Mixed extensions and document similarity stay outside batch selection. The final plan summarizes totals with expandable KEEP/QUARANTINE paths; validation and explicit confirmation remain required. Rescan to apply the new exclusion to existing inventories.
