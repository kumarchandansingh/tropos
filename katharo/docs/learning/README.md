# Learning track

Learning explanations do not replace authoritative implementation reference.

See the [decision and trade-off matrix](DECISION_TRADEOFFS.md) for alternatives, costs, revisit triggers, evidence, and interview probes.

## 1. Identity before algorithms

Question: are we comparing a location, an underlying file, bytes, or extracted content?

A path can change without changing bytes. Two hard-link paths can share one underlying file. A PDF can change bytes while preserving its text. Start each comparison by naming the identity layer.

## 2. Hashing versus similarity

SHA-256 answers equality: identical bytes have identical fingerprints. It is not a distance function. Word-shingle Jaccard compares sets of overlapping word sequences; it discovers revisions but cannot determine whether a resume targeting another job is disposable.

Exercise: create two text files with identical words and different whitespace. Observe different raw hashes but matching normalized-content evidence. Neither file becomes automatically actionable as a document match.

## 3. Parsing versus normalization

Parsing reads format syntax: PDF objects or DOCX XML. Normalization removes selected representation noise. Neither stage should invent business meaning. Empty extraction is unknown, not proof that two documents match.

## 4. Approval is a snapshot

A user approves observed evidence, not any future contents at the same path. Revalidate both selected extras and retained copies. File timestamps help reject stale observations; fresh content checks provide stronger evidence. A remaining race before the move requires stronger OS-level execution if threat assumptions expand.

## 5. Two systems, no shared transaction

SQLite can commit a record; the filesystem can rename a file. They cannot commit together as one transaction. Persist intent, perform the operation, persist its outcome, and reconcile unfinished states after crashes. This generalizes to payments, email delivery and object-store operations.

## 6. Enterprise translation

Desktop approval becomes ownership and policy approval. Folder scans become source adapters and change feeds. Quarantine becomes retention-governed disposition. Cross-source matching must respect permissions. More infrastructure is justified by scale and governance, not by a production label.
