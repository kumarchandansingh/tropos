# LLM Runtime Configuration

Tropos keeps provider credentials outside source control and loads them through a typed runtime boundary.

## Bootstrap configuration

The first runtime provider is Groq with `openai/gpt-oss-120b` as the default model.

Local and deployed runtimes provide these environment variables:

```text
TROPOS_LLM_PROVIDER=groq
TROPOS_LLM_MODEL=openai/gpt-oss-120b
TROPOS_GROQ_API_KEY=<secret>
```

Only `.env.example` is committed. Real `.env` files remain ignored by Git.

## Secret boundary

Application and domain code must not read provider secrets directly. `LLMRuntimeSettings` is the bootstrap boundary for provider configuration.

The API key:

- has no repository default;
- is excluded from object representation;
- is required only when a real provider adapter is constructed;
- causes the runtime to fail closed when absent.

This bootstrap is intentionally small. A later Admin-managed credential store can implement the same provider boundary without changing domain or evaluation code.

## Runtime boundary

The typed runtime now separates four product concepts:

```text
ModelProvider
  → ModelConnection
  → ModelDeployment
  → ModelAssignment
```

Application workflows depend on `LLMPort`, not provider SDK or HTTP response types. The first adapter is Groq and supports both text completion and strict Pydantic structured output.

Invocation metadata captures provider, connection, deployment, model, prompt version, latency, token usage, finish reason and provider request ID when available.

## Current scope

Implemented now:

- typed provider-neutral `LLMPort`;
- deterministic `FakeLLM`;
- Groq runtime adapter using the existing environment secret boundary;
- safe `tropos models test` smoke command;
- typed model/connection/deployment/assignment contracts.

Still intentionally deferred:

- evidence-sufficiency judge;
- grounded Resolve generation runtime;
- persistent encrypted Admin credential storage;
- provider fallback/circuit-breaker policy;
- model egress policy enforcement for restricted enterprise evidence.
