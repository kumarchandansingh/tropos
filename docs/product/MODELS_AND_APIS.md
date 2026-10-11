# Models & APIs Experience

Status: Active product and architecture contract  
Scope: Typed LLM runtime foundation

## User outcome

An AI/platform administrator can configure and test a model connection without coupling Resolve, Evaluation, or Training logic to a provider SDK or exposing the credential after setup.

The first executable configuration is environment-backed Groq. The product model is deliberately broader so a future Admin UI can manage multiple connections and role assignments without changing application contracts.

## Reference patterns

| Reference | Pattern adopted | Tropos interpretation |
|---|---|---|
| Dify model providers | Provider credentials are administered centrally rather than repeated inside every application | Model connection is a managed object separate from product workflows |
| Langfuse | Model, prompt, latency and token metadata are attached to invocations/traces | Invocation provenance belongs to each call, not only aggregate dashboards |
| Phoenix | Model/prompt/runtime variants should be comparable through evaluation evidence | A deployment may be assigned to a role, but quality claims belong to deployment + prompt/config + benchmark |

References:
- https://docs.dify.ai/
- https://langfuse.com/docs
- https://arize.com/docs/phoenix/

## Personas and user stories

Primary persona: AI / Platform Admin.

- As an admin, I want to configure a provider connection once and assign deployments to Tropos roles.
- As an admin, I want to test a connection without revealing the stored credential.
- As a quality owner, I want every invocation to record which provider, connection, deployment, model and prompt version produced it.
- As a product owner, I want sufficiency, generation and evaluation-judge roles to be independently assignable.
- As an operator, I want provider failures, timeout failures and malformed model output to remain distinguishable.

## Information architecture

```text
Models & APIs
├── Connections
├── Model Deployments
├── Role Assignments
└── Evaluation Evidence
```

This PR implements the object/runtime contract behind those surfaces. It does not add a visual frontend or persistent Admin credential store.

## UX flow

```text
Add connection
   ↓
Choose provider
   ↓
Supply credential
   ↓
Credential becomes masked/reference-only
   ↓
Test connection
   ↓
Healthy / authentication error / timeout / provider error
   ↓
Discover or define deployment
   ↓
Assign deployment to a role
   ├── Sufficiency
   ├── Generation
   ├── Eval judge
   └── Embedding
```

The bootstrap CLI exposes only the test step:

```text
tropos models test
```

It prints provider/deployment/latency/usage metadata and never prints the API key.

## Object model

```text
ModelProvider
   ↓ 1:N
ModelConnection
   ↓ 1:N
ModelDeployment
   ↓ N:M via assignment
ModelRole / ModelAssignment
```

### Object-model audit

| Concept | Decision |
|---|---|
| Provider | New typed product/runtime contract; provider name is not a quality score |
| Connection | New typed contract; stores a credential reference, never the secret itself |
| Deployment | New typed contract representing a concrete model identifier on one connection |
| Assignment | New typed contract mapping a Tropos role to a primary deployment and future fallbacks |
| LLM invocation | New typed metadata contract for latency, token usage, finish reason, request ID, prompt version |
| Capability-specific LangChain adapter | Keep for current Training/KA behavior, but replace untyped `model: Any` boundary with a protocol |
| Credential storage | Reuse current `LLMRuntimeSettings` environment bootstrap; persistent encrypted Admin storage is later |

## UI state contract

A connection card should eventually expose:

```text
Tropos Groq
Provider          Groq
Status            Healthy
Credential        ••••••••••
Last tested       ...
Deployments       1

[Test connection]
```

A role-assignment surface should expose:

```text
Role             Primary deployment        Fallbacks
Sufficiency      groq:gpt-oss-120b         —
Generation       groq:gpt-oss-120b         —
Eval judge       Not configured            —
Embedding        Existing embedding path    —
```

No UI should display a provider-level quality claim such as “Groq = 92%”. Quality evidence must be attached to the deployment + prompt/runtime configuration + benchmark.

## Functional architecture

```text
Runtime config / future Admin secret store
   ↓
Credential reference + secret resolver
   ↓
ModelConnection
   ↓
ModelDeployment
   ↓
LLMPort
   ├── complete_text
   └── complete_structured
   ↓
Provider adapter (Groq V1)
   ↓
Invocation metadata
```

The Groq adapter uses the OpenAI-compatible chat-completions HTTP boundary with strict JSON Schema for structured output. Provider-specific request/response handling is isolated inside the adapter.

## Security and failure behavior

- API keys are never committed and never included in object repr/output.
- Product/runtime objects carry `credential_reference`, not secret material.
- Provider error messages do not echo response bodies or credentials.
- Timeouts are explicit and bounded.
- Structured output is validated again with Pydantic after the provider returns it.
- A malformed structured response fails closed.
- CI uses `FakeLLM`/fake transport only; no production credential is required.
- Model egress policy remains a separate future control before restricted enterprise evidence is sent to any external provider.

## Invocation metadata

Every real call returns enough provenance for later tracing and evaluation:

- provider ID
- connection ID
- deployment ID
- model identifier
- prompt version
- latency
- input/output/total tokens when available
- finish reason
- provider request ID when available

Cost is intentionally not fabricated when the provider response does not contain a trustworthy billable-cost value. Cost calculation can be added through versioned pricing metadata later.

## Acceptance evidence

1. typed `LLMPort` supports text and Pydantic structured output;
2. `FakeLLM` provides deterministic tests;
3. Groq adapter uses the existing environment secret boundary;
4. strict structured output is revalidated before application code receives it;
5. invocation metadata captures model/prompt/latency/token provenance;
6. the credential never appears in repr or CLI output;
7. legacy capability adapters no longer accept an untyped `model: Any`;
8. a manual `tropos models test` command exercises the real configured model without making CI depend on secrets.
