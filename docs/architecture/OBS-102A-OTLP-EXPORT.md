# OBS-102A — Vendor-neutral OTLP export

**Status:** Proposed implementation in PR. **Destination undecided:** Splunk, Grafana/Tempo and Jaeger remain options for OBS-102B.

## Scope

Tropos already emits live parent/child OpenTelemetry spans in OBS-101B. OBS-102A exports those same spans over **OTLP/HTTP** to a local OpenTelemetry Collector. The Collector deliberately forwards only to its debug exporter.

This does **not** add LangSmith, a vendor monitoring SDK, a hosted service, business metrics or an AI-quality evaluator.

## Architecture

```text
Tropos Resolve request
  -> OpenTelemetry live spans (OBS-101B)
  -> OTLP HTTP exporter (opt-in)
  -> local Collector (:4318)
  -> debug output (Docker logs)
```

## Local Windows setup (PowerShell)

Prerequisites: Docker Desktop is running; Tropos is checked out under `C:\Users\91963\tropos`; Ollama and Groq configuration remain separate.

1. Start the collector from the repository:

```powershell
docker compose -f "C:\Users\91963\tropos\infra\observability\compose.yaml" up -d
```

2. In the terminal that starts the Tropos API, enable the OTLP exporter and install the **optional** OTLP/HTTP library for that run (no paid account, no credential, no lockfile change):

```powershell
Set-Location "C:\Users\91963\tropos\apps\api"
$env:TROPOS_OTEL_OTLP_ENDPOINT = "http://127.0.0.1:4318/v1/traces"
$env:TROPOS_EMBEDDING_PROVIDER = "ollama"
$env:TROPOS_EMBEDDING_MODEL = "nomic-embed-text"
$env:TROPOS_EMBEDDING_DIMENSIONS = "768"
uv run --with "opentelemetry-exporter-otlp-proto-http>=1.45,<2" tropos web --host 127.0.0.1 --port 8000
```

If port 8000 is already occupied, stop your old Tropos web instance first. The exporter is **disabled by default**. The `uv run --with` option installs the exporter into the invocation's environment; it does not persist a dependency in the project's lockfile. A follow-on PR should pin the optional dependency and update `uv.lock` before production release.

3. Submit an actual Resolve request in the Tropos web UI. Verify the Collector received spans:

```powershell
docker compose -f "C:\Users\91963\tropos\infra\observability\compose.yaml" logs --tail 150 collector
```

Look for `resolve.request` and `resolve.retrieval` under the same trace ID, with matching parent/child span context. The debug logs are the **OBS-102A acceptance evidence**, not a searchable trace-waterfall dashboard.

## Privacy and security

- The existing live span recorder intentionally emits only operation names, `tropos.mapping_mode`, and exception **type** (not exception message).
- Do not add raw queries, answers, evidence, tenant IDs, secrets or URLs containing credentials to spans.
- Bind Collector port 4318 to local loopback; Docker console output is for local smoke tests only.
- Keep production headers and authentication in deployment settings, never committed to source.
- `TROPOS_OTEL_CONSOLE=1` continues to enable console output independently.

## Test gate

```powershell
Set-Location "C:\Users\91963\tropos\apps\api"
uv run pytest tests/unit/core/test_otlp_runtime.py tests/unit/core/test_live_opentelemetry.py
```

## Definition of done

- [ ] CI passes tests, lint, type checking and lockfile checks.
- [ ] Local Collector receives one Resolve execution as correlated OTLP spans.
- [ ] Export is opt-in; existing JSONL traces and console mode remain intact.
- [ ] Raw request and evidence stay out of telemetry.
- [ ] Selected visualization backend remains an explicit **OBS-102B ADR**.
