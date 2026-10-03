# Architecture

Katharo is a local modular monolith. Domain selection rules are independent of HTTP and persistence. The composition root wires concrete adapters; protocols and additional source adapters should be introduced when another implementation is needed.

| Module | Owns |
| --- | --- |
| `domain.py` | Observations, extraction vocabulary, selection invariants |
| `filesystem.py` | Path guard, identity, hashing, byte verification |
| `documents.py` | Parsing, normalization, shingle comparison, process timeout |
| `scanner.py` | Inventory and comparison orchestration |
| `store.py` | SQLite records and serialized writes |
| `actions.py` | Prepared plans, quarantine and restore journal |
| `server.py` | Loopback HTTP, background jobs, native picker and composition |
| `web/` | Apple-inspired interface, selection and explicit confirmation |

## Evidence identity

File observation IDs hash the absolute path and identify a location in a scan. Filesystem identity is device plus inode; Windows path stat is used because directory-entry stat may omit inode. This is not a portable identity across drives.

The raw SHA-256 hashes exact file bytes. Size filtering avoids reading singleton-size non-documents. Hashes group candidates; byte verification occurs during execution. No hash cache is currently reused across scans.

The canonical document fingerprint hashes `canonical-text-v1` and normalized extracted text. Normalization applies NFC and whitespace compaction; words and punctuation remain. It is not Tropos's richer title-and-block serialization and does not claim to preserve every layout distinction.

Revision candidates use five-word shingle Jaccard overlap, at 0.72 or higher. This discovery threshold is a provisional heuristic; it never permits a cleanup action. Matching text also remains review-only. Candidate comparison is bounded to 300 documents and is quadratic inside that bound; an inverted shingle index is planned for larger collections.

## Local server

Static resources are bundled. The HTTP server binds 127.0.0.1; Host validation mitigates DNS rebinding, and POST requests require an unpredictable session token plus an allowed Origin. No CORS permission is issued. Use only as a local desktop service, not internet hosting.

One background scan runs at a time. Mutating operations are serialized. Parsing runs in spawned workers with per-document timeouts. Memory limits and OS sandboxing remain planned.

## Actions and consistency

Plan states: `prepared → executing → completed/partial → restored/partial`.

Item states: `planned → moving → quarantined → restoring → restored`, with `failed` and an error reason when a move does not complete.

Before moving: revalidate selected and retained observations, hash contents again, compare bytes, guard paths. Same-device moves rename into an exclusively created item directory. Cross-device moves copy exclusively, flush, hash the destination, revalidate source and keeper, then remove the source.

SQLite records intent and outcomes. An atomically replaced manifest in the quarantine plan directory records original paths. Database and filesystem cannot share an atomic transaction; unfinished states require reconciliation. No automatic permanent deletion, overwrite, plan re-execution, or blind retry is permitted.

Known limitation: there is a remaining race between revalidation and path-based file operations. Stronger handle-based Windows execution is planned. The app assumes a trusted single-user machine and does not claim adversarial filesystem safety.
