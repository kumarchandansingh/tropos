# Safe Embedded HTML Data Extraction

Status: Design for implementation  
Scope: Deterministic ingestion of structured, data-bearing JavaScript literals embedded in HTML without executing JavaScript.

## 1. User / business problem

The live Tropos test exposed a false sense of successful ingestion.

A 29 KB retail analytics HTML file was accepted, but its business content lived inside a JavaScript data structure used by the page renderer. The existing HTML parser intentionally skipped all `<script>` content, so only the static shell was persisted. Retrieval and sufficiency then behaved correctly against an incomplete corpus.

This creates a dangerous product failure mode:

    source accepted
    → ingestion says available
    → only shell text persisted
    → relevant questions abstain or retrieve unrelated evidence

Tropos needs to distinguish executable JavaScript from deterministic structured content embedded inside JavaScript.

## 2. Personas / use cases

### AI / Platform Admin
- uploads an HTML artifact exported from an internal analytics or documentation app;
- expects data-bearing content to become searchable even if the page uses client-side rendering;
- must not trigger JavaScript execution during ingestion.

### Support / Resolve User
- asks questions against the actual business content rather than the HTML shell.

### Security / Access Admin
- requires scripts to remain untrusted input;
- must not permit arbitrary code execution, network access, DOM evaluation, or browser automation during canonical ingestion.

Failure cases:
- arbitrary executable script: ignore;
- template literals / functions / expressions: reject from structured-data extraction and continue with visible HTML only;
- malformed literal: ignore that literal, do not execute or guess;
- data duplicated in rendered HTML and embedded state: avoid material duplication where possible;
- tiny config blobs: ignore as noise.

## 3. Reference patterns

Patterns considered:
- static site / SPA hydration payloads, where data is embedded as JSON or JavaScript literals and rendered client-side;
- structured-data ingestion, which separates data extraction from application execution;
- browser security principle: parse untrusted data; do not execute untrusted code.

Tropos deliberately does **not** introduce Playwright, Selenium, a JavaScript VM, browser rendering, or remote resource loading in canonical ingestion.

## 4. Information architecture / UX impact

No new top-level navigation is required.

Sources & Ingestion should continue to show the normal canonical result, but the source is now materially complete enough for downstream retrieval.

A later ingestion-detail view may expose:
- parser strategy;
- visible-text bytes;
- embedded-data assignments extracted;
- embedded-data assignments skipped.

Those diagnostics are deferred from this PR unless already available through trace/run metadata.

## 5. Object / data model audit

| Need | Existing concept | Decision |
|---|---|---|
| Raw HTML evidence | RawKnowledgeRecord.payload | Reuse unchanged |
| Parsed visible HTML | ExtractedKnowledgeText | Reuse |
| Embedded structured content | Parsed text contribution | Reuse inside ExtractedKnowledgeText; do not create a parallel knowledge entity |
| Parser strategy identity | absent | Add deterministic parser strategy version |
| Reprocessing after parser upgrade | current replay keyed only by raw ingestion fingerprint | Add processing-version-aware run identity |
| Canonical version decision | normalization/content fingerprint | Reuse |
| Chunking | DeterministicKnowledgeChunker | Reuse |

Raw source identity remains independent from processing strategy. A parser upgrade must not falsify the source version or raw payload fingerprint.

## 6. Functional architecture

    Raw HTML bytes
       ↓
    UTF-8 decode
       ├── visible DOM text parser
       │      └── existing deterministic Markdown blocks
       │
       └── inline script collector
              ↓
          assignment detector
              ↓
          balanced literal extraction
              ↓
          safe JS-literal → Python-literal normalization
              ↓
          ast.literal_eval
              ↓
          strict type validation
              ↓
          human-readable text density gate
              ↓
          deterministic Markdown rendering
       ↓
    visible text + accepted embedded data
       ↓
    existing normalizer
       ↓
    canonical fingerprint
       ↓
    existing versioning / chunking / indexing

No JavaScript executes anywhere in this flow.

## 7. Safe extraction contract

Eligible script content must satisfy all of the following:

1. inline script only; external `src` scripts are not fetched;
2. assignment begins with `const`, `let`, or `var`;
3. assigned value starts with `[` or `{`;
4. value is extracted with bracket balancing that respects quoted strings and escapes;
5. template literals are not supported;
6. unquoted object keys and `true/false/null` may be normalized deterministically;
7. parsing uses `ast.literal_eval`, never `eval` or `exec`;
8. resulting structure may contain only:
   - dict with string keys,
   - list,
   - string,
   - int / float,
   - bool,
   - null/None;
9. accepted structure must cross a minimum human-readable text threshold;
10. rendered embedded text is skipped when it is substantially duplicated by visible HTML text.

Unknown expressions, function calls, identifiers, operators, DOM access and code are therefore rejected automatically.

## 8. Rendering contract

The structured literal is converted to Markdown so the existing normalizer and chunker can preserve useful boundaries.

Example:

    const CARDS = [
      {
        title: "Low conversion rate",
        problem: "...",
        analytics: "...",
        steps: [...]
      }
    ]

becomes conceptually:

    ## Embedded data: CARDS

    ### Low conversion rate

    - problem: ...
    - analytics: ...

    #### steps
    - Funnel diagnosis: ...
    - Root cause analysis: ...

The current 1,200-character structural chunker then produces multiple meaningful chunks instead of one shell chunk.

## 9. Processing-version / replay architecture

Today exact source replays short-circuit before parsing because ingestion idempotency is keyed by raw ingestion fingerprint.

That is correct for the same **source + processing strategy**, but it prevents a source from being reprocessed when parser behavior changes.

This build introduces a processing-version dimension for ingestion runs:

    raw ingestion fingerprint
    + processing version
    → completed-run identity

Rules:
- raw payload/source identity does not change;
- same raw source + same processing version → idempotent replay;
- same raw source + newer processing version → reprocess through parser/normalizer/chunker;
- canonical versioning still decides whether a new knowledge version is required.

SQLite migration expands run uniqueness from:

    (knowledge_id, ingestion_fingerprint)

to:

    (knowledge_id, ingestion_fingerprint, processing_version)

Existing runs are migrated as `ingestion-pipeline-v1`.

The new runtime uses `ingestion-pipeline-v2-embedded-html-data`.

## 10. Security

- never execute JavaScript;
- never fetch external scripts/resources;
- never instantiate a browser;
- bound script/literal sizes;
- fail closed on unsupported JavaScript syntax;
- preserve original raw bytes for audit;
- do not treat embedded script content as instructions to the model; it remains untrusted knowledge data;
- authorization/access policy remains attached before retrieval and model egress.

## 11. Observability

The immediate acceptance evidence is deterministic:
- parser output contains expected embedded data;
- chunk count materially increases for the retail fixture;
- retrieval finds footfall/conversion/basket concepts.

Future ingestion diagnostics should expose parser strategy and extraction counts.

## 12. Acceptance evidence

1. ordinary HTML script such as `alert('ignore')` remains excluded;
2. safe inline data assignment is extracted without execution;
3. functions / expressions are ignored;
4. the representative retail-style `CARDS` structure yields searchable footfall, conversion and basket-size text;
5. embedded content is rendered into multiple structural chunks;
6. exact duplicate under the same processing version replays;
7. the same source under a newer processing version reprocesses rather than replaying stale parser output;
8. raw source version/fingerprint remains unchanged across processing-version upgrades;
9. existing parser, normalization, ingestion and retrieval tests stay green;
10. strict mypy, Ruff and CI pass.

## 13. Deferred

- browser rendering / DOM execution;
- JSON-LD-specific semantic modeling;
- Next.js `__NEXT_DATA__` special adapters;
- framework-specific hydration payload adapters;
- external script fetching;
- OCR/PDF;
- model-assisted HTML extraction;
- admin controls for custom embedded-data selectors.

Complexity should be added only when measured source failures justify it.
