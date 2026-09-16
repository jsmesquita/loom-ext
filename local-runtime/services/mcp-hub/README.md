# MCP Hub

User-facing MCP facade (ADR 0007 / 0008 / 0010 / **0011** / **0012** / **0015**).
Discovers MCP Clients on `initialize`. Admin grants catalog tools **per
IdP profile**. IDE auth = **OAuth against the active IdP** — **no mint**.
Ops UI (plugin) calls Hub `/v1/*` with the **same SPA JWT** (no Loom BFF).

```text
IDE (URL only)
  → 401 + Protected Resource Metadata
  → Active IdP Authorization Code + PKCE
  → Bearer access_token (aud=loom-mcp-hub [+ loom-frontend dual-aud])
  → mcp-hub validates JWKS → grants ∩ Loom catalog (user JWT)
      → tools/call → MCP upstream HTTP
      → agent__* → /api/agents (+ SSE)

Loom SPA plugin
  → Bearer SPA JWT (aud=loom-frontend) + mcp:read/write groups
  → http://127.0.0.1:8790/v1/clients|analytics|…
```

Host port loopback-only (`127.0.0.1:8790`). Health: `GET /health`.
PRM: `GET /.well-known/oauth-protected-resource`.
Public info: `GET /v1/info`.
Store: **`MCP_HUB_DATABASE_URL`** (Postgres DB `mcp_hub`).

## Cursor `mcp.json`

```json
{
  "mcpServers": {
    "loom-hub": {
      "url": "http://127.0.0.1:8790/mcp",
      "auth": {
        "CLIENT_ID": "loom-mcp-hub",
        "scopes": ["openid", "profile"]
      }
    }
  }
}
```

Do **not** put `Authorization` headers. Use static `auth.CLIENT_ID` so Cursor
skips Dynamic Client Registration.

## Env

| Variable | Purpose |
|----------|---------|
| `LOOM_BACKEND_URL` | Hub → backend (user JWT / dual-aud) |
| `LOOM_ACCESS_TOKEN_MODE` | `dual_aud` (default) or `token_exchange` |
| `MCP_HUB_DATABASE_URL` | Postgres DSN for Hub store (dedicated DB `mcp_hub`) |
| `MCP_HUB_STORE_PATH` | Optional JSON path (fallback / migrate source) |
| `MCP_HUB_RESOURCE` | Canonical resource URL (aud/resource check) |
| `MCP_HUB_OIDC_ISSUER` | Token `iss` (browser URL of the **active** IdP) |
| `MCP_HUB_OIDC_AUDIENCE` | Default `loom-mcp-hub` (IDE MCP) |
| `MCP_HUB_ADMIN_AUDIENCES` | Default `loom-frontend,loom-mcp-hub` (ops `/v1/*`) |
| `MCP_HUB_CORS_ORIGINS` | Browser origins for plugin ops |
| `MCP_HUB_OIDC_JWKS_URL` | JWKS reachable from container |

Contract: `2026-09-hub-1`. Docs: ADR 0011 / 0012 / 0015, specs 017 / 024 / 025.

## Package layout (hexagonal strangler)

```text
mcp_hub/
  domain/           # pure rules (access, naming, identity, errors, records)
  application/      # ports + wiring + use_cases
  adapters/
    inbound/        # http_app (http.server)
    outbound/       # file_store, pg_store, loom_http, oauth_jwks
  __main__.py
```

Wire protocol and env unchanged for MCP. Store default = Postgres via
`MCP_HUB_DATABASE_URL` (`HubStore` port). Fresh postgres volume runs
`etc/docker/postgres-init/02-mcp-hub-db.sql`. Existing volumes need reset or
manual `CREATE DATABASE mcp_hub`.
