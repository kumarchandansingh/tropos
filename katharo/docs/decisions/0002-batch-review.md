# ADR 0002: batch exact duplicates, review exceptions

Status: Accepted.

Many tiny Office owner records overwhelm review and look like unrelated documents. Exclude names starting with `~$` from inventory and report their count. Keep full-byte matching separate from extracted text.

Offer one selection action for exact groups with one extension. Retain the suggested keeper, respecting explicit keeper choices and keep-all decisions. Mixed extensions require individual review even when raw bytes match. Collapse groups, sort by recoverable bytes, and summarize the final plan with expandable KEEP/QUARANTINE paths.

Batch selection is a proposal, not execution permission. Existing exact-only, retain-one and fresh-content validation remain unchanged. Keeper ranking is a filename/path heuristic, not a claim of user preference. Cross-scan preferences and pagination remain planned.
