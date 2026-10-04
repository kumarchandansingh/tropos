# Product model

Katharo helps a single user review repeated personal files without confusing byte identity, matching document text, and meaningful revisions.

The workflow is folder selection → evidence gathering → analytics → individual decisions → reviewed cleanup plan → explicit approval → quarantine → optional restore.

## Decisions

- Retain this exact copy.
- Select extra exact copies for quarantine.
- Keep all copies.
- Keep document revisions for different purposes.
- Reopen a review decision.

Recommendations use filename suffixes and path length only to order a default keeper; these clues never establish equality. Users can choose another keeper.

Quarantine is a real folder outside the scan root. Each plan has a unique directory and original-path manifest. A virtual review queue precedes every move. Permanent deletion is outside the implemented product.

Analytics distinguish scanned logical bytes, exact-extra logical bytes, selected bytes, and review-only document candidates. These are not claims about actual filesystem allocation, compression, or space already freed.

## Planned

OCR, visual previews, highlighted text diffs, job-target labels, cross-scan decision reconciliation, categorization and index export. Decisions are currently persisted per scan; they are not yet restored automatically into a later scan's UI.
