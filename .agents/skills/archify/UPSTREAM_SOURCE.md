# Third-party Archify skill vendoring

**Source:** https://github.com/tt-a1i/archify
**Release:** `v3.0.1`
**Pinned upstream commit:** `2ab3cae7ac2c2a55d7386ca789d03c4fcd31816c`
**License:** MIT, see `LICENSE` and `THIRD_PARTY_NOTICES.md`.

This directory is a documentation-tool dependency only. It contains the upstream skill entry point, runtime engine, schemas, reference guides, representative examples and required renderer assets, copied from the pinned commit without modifications. Upstream development tests and large demonstration-only examples are intentionally not vendored; use the full upstream repository for its own test suite.

No Tropos production runtime imports these files. Updates require a deliberate, reviewed vendor refresh. The Archify update reminder is disabled in our pilot workflow using `ARCHIFY_UPDATE_CHECK_DISABLED=1`.
