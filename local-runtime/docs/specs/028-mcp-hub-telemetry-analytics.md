# Spec 028 — Telemetria e analytics do MCP Hub

- **Status:** Aceito (implementado baseline A–D, 2026-09-14)
- **Data:** 2026-09-14
- **Implementa:** plano [mcp-hub-telemetry-analytics-plan.md](../backlog/mcp-hub-telemetry-analytics-plan.md),
  [Spec 020](020-mcp-hub-observability.md)
- **Depende de:** [021](021-mcp-hub-clients.md), [025](025-mcp-hub-agents-as-tools.md)

## 1. Objetivo

Persistir eventos de tráfego Hub + metadados de runs `agent__*` para
visões de **uso**, **adesão** e **FinOps**, sem logar secrets/args/prompt.

## 2. Extension — `hub_telemetry_events` (DB `mcp_hub`)

| Coluna | Tipo | Notas |
|--------|------|--------|
| `id` | BIGSERIAL | PK |
| `occurred_at` | TIMESTAMPTZ | default now() |
| `event_type` | TEXT | `initialize` \| `tools_list` \| `tools_call` \| `admin_patch` \| `admin_grants` |
| `request_id` | TEXT | uuid |
| `hub_session_id` | TEXT | nullable |
| `mcp_client_slug` | TEXT | |
| `subject_hash` | TEXT | sha256 trunc 16 hex |
| `idp_groups` | JSONB | lista de groups |
| `tool_name` | TEXT | |
| `original_tool` | TEXT | |
| `server_id` | INT | |
| `phase` | TEXT | `ok` \| `denied` \| `error` \| … |
| `error_code` | TEXT | |
| `duration_ms` | INT | |
| `meta` | JSONB | tool_count, server_count, wait_mode, agent_id, loom_session_id, … |

`last_seen_at` em `hub_clients` atualiza em **initialize, list e call**.

Writer best-effort: falha de insert **não** quebra JSON-RPC.

## 3. Core — invocations / sessions (autorizado)

Colunas em `invocation_sessions`:

- `source` (`chat` \| `mcp_hub`)
- `mcp_client_slug`
- `hub_session_id`

Colunas em `invocations`:

- `source`, `mcp_client_slug`, `hub_session_id`, `wait_mode`
- timings já existentes preenchidos no path Hub
- tokens/cost a partir de `session_end` SSE

Tabela `invocation_tool_spans`:

- `invocation_id`, `server_name`, `tool_name`, `duration_ms`, `status`, `error_code`, `created_at`

## 4. APIs

```text
GET /v1/analytics/summary?hours=24     # Hub (service token)
GET /v1/analytics/tools?hours=24&slug=
GET /v1/analytics/errors?hours=24&limit=100  # recent denied/error events + by_code
GET /api/mcp/hub/analytics/summary     # BFF proxy + FinOps join Core
GET /api/ext/local-runtime/analytics/summary
GET /api/ext/local-runtime/analytics/errors
```

## 5. Privacy

- `subject` em claro **não** na tabela de events (só hash).
- Sem `arguments`, prompt ou response nos events.
- Motivo operacional curto permitido em `meta.reason` (≤ ~280 chars, redacted),
  ex.: falha stdio / HTTP — **não** corpo de tool result.
- Escopo read: `mcp:read`.

## 6. Critérios de aceite

- [x] Spec neste arquivo
- [x] list/call gravam rows; deny com phase=denied
- [x] last_seen move em call
- [x] invocation Hub tem slug + duration + tokens quando SSE envia
- [x] UI Operate → Hub analytics: Overview / Tools / Errors / Adoption / FinOps
