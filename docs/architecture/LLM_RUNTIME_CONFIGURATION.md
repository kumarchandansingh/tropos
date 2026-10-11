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

## Current scope

This change provisions configuration only. It does not yet implement the Groq adapter, evidence-sufficiency judge, grounded generation, provider fallback, or persistent secret storage.
