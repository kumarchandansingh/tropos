# Local Web Origin Security Hardening

Status: Design for implementation  
Scope: close the confirmed cross-site request and DNS-rebinding exposure in the localhost Tropos product slice.

## 1. User / business problem

The local Tropos web server accepts requests from any Host/Origin and mutating POSTs do not require a browser-held anti-CSRF/session token.

A malicious website opened while Tropos is running can therefore attempt to:
- ingest attacker-controlled content into an arbitrary tenant/group;
- trigger Resolve calls and model spend;
- trigger embedding materialization and send governed chunks to the embedding provider;
- read diagnostics after DNS rebinding if the browser is tricked into resolving an attacker-controlled hostname to localhost.

This risk became materially larger once semantic indexing could trigger external embedding calls.

## 2. Personas / use cases

### Local operator
- starts Tropos on localhost;
- uses the embedded browser UI;
- expects unrelated websites to be unable to invoke Tropos;
- can still use the CLI independently.

### Security reviewer
- needs deterministic controls at the HTTP boundary rather than relying on browser defaults.

Failure cases:
- foreign Host header;
- foreign Origin header;
- missing/incorrect session token;
- JSON endpoint called with a simple cross-site content type such as text/plain;
- non-loopback bind attempt.

## 3. Reference patterns

The selected controls follow standard local-development web hardening patterns:
- validate Host to block DNS rebinding;
- bind only to loopback for a local-only product slice;
- validate Origin on browser POSTs;
- require a random per-process token in a custom request header;
- require exact JSON content type for JSON endpoints.

No CORS permission is added.

## 4. Information architecture / UX

No new workspace.

At server startup Tropos prints:
- the local URL;
- a short statement that local request protection is enabled.

The browser receives the random token only inside the served same-origin HTML and automatically sends it in the `X-Tropos-Session-Token` header on every POST.

The token is not shown in normal page UI or runtime diagnostics.

## 5. Domain / data-model audit

No domain entities change.

This is an HTTP transport security boundary around existing product operations.

New process-local concept:
- LocalWebSecurityContext
  - session token
  - allowed loopback hosts
  - actual bound port
  - expected same-origin values

It is not persisted.

## 6. Functional architecture

    browser loads /
      ↓
    Host validation
      ↓
    HTML rendered with random process token
      ↓
    browser POST
      ├── Host must match localhost/127.0.0.1 + actual port
      ├── Origin must match same local origin when present
      ├── X-Tropos-Session-Token must match
      └── endpoint-specific Content-Type must match
      ↓
    existing API handler

Foreign requests fail before body processing, provider calls, ingestion or tenant/group parsing.

## 7. Security decisions

### Loopback binding
`tropos web` only accepts `127.0.0.1` or `localhost` in this local product slice.

### Host validation
Accept only:
- `127.0.0.1:<actual-port>`
- `localhost:<actual-port>`

Any other Host returns 421 Misdirected Request.

### Origin validation
For POST:
- if Origin is present, it must be exactly `http://127.0.0.1:<port>` or `http://localhost:<port>`;
- foreign/null origins are rejected;
- non-browser clients may omit Origin but still require the session token.

### Session token
A cryptographically random token is generated once per server process.
Every POST requires:
`X-Tropos-Session-Token: <token>`.

The embedded UI receives the token by server-side placeholder substitution and automatically adds it to POST requests.

### Content type
- `/api/resolve` requires exactly `application/json` ignoring optional charset parameters;
- `/api/embeddings/materialize` requires `application/json`;
- `/api/ingest` permits `application/octet-stream` and a bounded allow-list of supported file MIME types, but still requires token + same-origin checks.

### Diagnostics
Runtime diagnostics stop exposing:
- repository root;
- Python executable;
- working directory;
- absolute module paths;
- absolute database path.

They retain build/version/strategy/count information.

## 8. Acceptance evidence

1. foreign Host GET is rejected before diagnostics are returned;
2. foreign Origin POST is rejected;
3. missing/incorrect session token POST is rejected;
4. text/plain JSON requests are rejected;
5. valid same-origin browser-style resolve request succeeds;
6. valid ingest remains functional;
7. valid semantic materialization reaches the existing runtime path;
8. tenant/group query parameters are never parsed before POST security checks pass;
9. diagnostics contain no absolute local paths;
10. non-loopback server bind is rejected;
11. existing product tests remain green.

## 9. Deferred

- authenticated multi-user web sessions;
- TLS;
- remote/network deployment;
- role-based diagnostics;
- production CSRF framework;
- reverse-proxy trust configuration.

Those belong to a hosted product surface rather than this local-only slice.
