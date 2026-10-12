# Runtime Diagnostics — Local Operator Contract

Status: Design for implementation  
Scope: make the local Tropos runtime self-identifying so operators can verify which code, parser, database, chunker, retrieval strategy and model configuration produced a result.

## 1. User / business problem

Live debugging exposed a product-operability gap: the browser can show an ingestion result, but it cannot prove which local code or package instance produced it.

For an operator, “Chunks written: 1” is not enough. They need to answer:

- Which Git commit am I actually running?
- Which parser strategy is active?
- Which processing version controls ingestion replay?
- Which Python/module path is loaded?
- Which SQLite database is this server using?
- Which chunker and retrieval strategy are active?
- How many current chunks exist in the database?
- Which model/provider is configured?
- Is this a stale server/package or the expected runtime?

Without that, browser behavior can be mistaken for a parser defect when the wrong process or module is actually running.

## 2. Personas

### AI / Platform Admin
Needs a self-service runtime identity panel before debugging ingestion/retrieval.

### AI Quality / Product Owner
Needs execution lineage that ties UI behavior to a concrete build/configuration.

### Support / Resolve User
Does not need the raw diagnostics by default; the panel belongs under Observability.

## 3. Reference patterns

Durable patterns borrowed from mature operational products:
- build/version identity shown in system/about pages;
- runtime configuration surfaced separately from user data;
- health and diagnostics expose environment facts but never secrets;
- observability distinguishes captured facts from unavailable facts.

This extends the existing Tropos Observability workspace rather than creating a new top-level page.

## 4. Information architecture

    Observability
    ├── Runtime summary
    ├── Runtime diagnostics
    │   ├── Build
    │   ├── Python/module identity
    │   ├── Ingestion
    │   ├── Storage
    │   ├── Retrieval
    │   └── Model
    ├── Recent traces
    └── Trace detail

## 5. UI states

### Happy state

The diagnostics panel shows explicit values:

- Git commit / branch when discoverable;
- parser strategy;
- ingestion processing version;
- chunking strategy and max characters;
- retrieval strategy;
- database path, existence, size, current knowledge/chunk counts;
- Python executable/version;
- loaded Tropos web/parser module paths;
- provider/model/configured state.

### Partial state

When Git metadata is unavailable (for example, packaged deployment without a .git directory), show:

    Git commit: Not available

Do not fail the whole endpoint.

### Failure state

If database introspection fails, return diagnostics with a storage error field rather than hiding the rest of the runtime identity.

## 6. Domain / data-model audit

No new domain entities are needed.

This is a read-only operational projection over:
- parser/chunker/runtime class metadata;
- current working process;
- SQLite metadata;
- model runtime settings;
- fixed retrieval strategy identifier.

No knowledge content, prompts, API keys or raw evidence are exposed.

## 7. Functional architecture

    Browser Observability
       ↓
    GET /api/runtime-diagnostics
       ↓
    Runtime diagnostics projection
       ├── Git metadata
       ├── Python/module paths
       ├── parser strategy
       ├── processing version
       ├── chunker strategy/config
       ├── SQLite stats/path
       ├── retrieval strategy
       └── model provider/model/configured
       ↓
    diagnostics card

## 8. Technical decisions

- Use fixed-argument local `git rev-parse` commands only when a repository can be discovered from the loaded module path.
- Git lookup is optional and bounded; failure returns null values.
- Expose public strategy/version properties rather than reading private fields from UI code.
- SQLite diagnostics are read-only.
- Database path is acceptable in this localhost-only operator slice; remote/multi-user deployment will need role-gated diagnostics.
- Never return the API key, environment variables, Authorization headers or prompt/evidence content.

## 9. Acceptance evidence

1. endpoint returns the loaded parser strategy;
2. endpoint returns ingestion processing version;
3. endpoint returns chunking strategy/max characters;
4. endpoint returns retrieval strategy;
5. endpoint returns exact database path plus current chunk/knowledge counts;
6. endpoint returns loaded Python executable/module paths;
7. endpoint returns provider/model/configured without the secret;
8. Git commit/branch are returned when repository metadata is available and null otherwise;
9. Observability renders diagnostics with truthful “Not available” values;
10. tests prove secret values are absent.

## 10. Deferred

- remote deployment build metadata service;
- environment/version comparison across nodes;
- signed build provenance;
- role-gated diagnostics;
- downloadable support bundle;
- automatic mismatch alerting between frontend/backend builds.
