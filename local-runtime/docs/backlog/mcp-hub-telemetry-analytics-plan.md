# Plano — Telemetria MCP Clients (uso, adesão, FinOps)

- **Status:** Implementado (A0–D1 baseline)
- **Data:** 2026-09-14
- **Área:** Hub MCP + BFF (agents) + agent-runtime (fase 3)
- **Alinha:** [Spec 020](../specs/020-mcp-hub-observability.md),
  [021](../specs/021-mcp-hub-clients.md),
  [010](../specs/010-local-mcp-observability.md),
  [013](../specs/013-local-agent-runtime-observability.md),
  [ADR 0002](../adr/0002-postgresql-as-relational-datastore.md) (analytics em PG)
- **Backlog:** [REF-2026-09-14-10](refactoring.md)

## 1. Objetivo

Passar a **persistir** o que já existe em request/runtime, para montar:

| Visão | Pergunta |
|-------|----------|
| **Uso** | Quais clients, tools e agents geram tráfego? Latência / erros? |
| **Adesão** | Quem adotou o Hub? Funil list → call → agent? Grants vs uso real? |
| **FinOps** | Custo por client / subject / agent / período (tokens + runtime)? |

Princípios:

1. **Extension-first** — fatos de Hub em DB `mcp_hub` (ou schema dedicado).
2. **Core só com autorização** — enriquecer `invocations` / joins FinOps.
3. **Sem secrets / args completos** — Spec 020; `subject_hash` em prod.
4. **Append-only events** + agregações opcionais depois (sem Kafka no v1).
5. **Não bloquear o hot path** — write async ou fire-and-forget com best-effort.

## 2. Lacunas atuais (resumo)

| Disponível agora | Persistido hoje |
|------------------|-----------------|
| `tools/list` / `tools/call` (slug, tool, server, denied, duration) | Quase só log (Spec 020 incompleto) |
| `initialize` → client + binding | `hub_clients`, `hub_session_bindings` |
| `last_seen` | Só no initialize (não no call) |
| `agent__*` → session/invocation | Sem `mcp_client_slug` / `hub_session_id` / `wait_mode` |
| Timing Hub async | Colunas Loom existem; path Hub pouco preenche |
| Tools internas do agent (ADO…) | Não ligadas ao client Hub |
| Tokens / cost em `invocations` | Chat/AgentCore; Hub local parcial |

## 3. Modelo de dados alvo

### 3.1 Fase A — Hub events (extension, DB `mcp_hub`)

```sql
-- Pseudo-DDL (nome final na spec de implementação)
CREATE TABLE hub_telemetry_events (
  id              BIGSERIAL PRIMARY KEY,
  occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  event_type      TEXT NOT NULL,  -- tools_list | tools_call | initialize | admin_grant_change
  request_id      UUID NOT NULL,
  hub_session_id  TEXT,
  mcp_client_slug TEXT,
  subject_hash    TEXT,           -- sha256 truncado
  idp_groups      TEXT[],         -- ou JSONB compacto
  tool_name       TEXT,           -- nullable (list)
  original_tool   TEXT,
  server_id       INT,
  phase           TEXT,           -- start|end|ok|denied|error (call)
  error_code      TEXT,
  duration_ms     INT,
  meta            JSONB NOT NULL DEFAULT '{}'
  -- meta examples: tool_count, server_count, agents_enabled_effective,
  --                wait_mode, agent_id, loom_session_id, loom_invocation_id
);

CREATE INDEX hub_telemetry_occurred_idx ON hub_telemetry_events (occurred_at DESC);
CREATE INDEX hub_telemetry_slug_idx ON hub_telemetry_events (mcp_client_slug, occurred_at DESC);
CREATE INDEX hub_telemetry_type_idx ON hub_telemetry_events (event_type, occurred_at DESC);
```

**Também na Fase A:**

- Atualizar `hub_clients.last_seen_at` em **todo** `tools/list` e `tools/call` (não só initialize).
- Evento `admin_grant_change` / patch client (slug, group, before/after hash — sem dump enorme).

### 3.2 Fase B — Ligação agents Hub ↔ Loom (Core, **autorizar**)

Colunas opcionais em `invocation_sessions` e/ou `invocations`:

| Campo | Uso |
|-------|-----|
| `source` | `chat` \| `mcp_hub` \| … |
| `mcp_client_slug` | adesão por canal |
| `hub_session_id` | correlação Spec 020 |
| `wait_mode` | `accepted` \| `complete` |
| `hub_request_id` | request_id Hub |

Preencher em `mcp_hub_agents.start_agent_run` / `_consume_local_stream`:

- `client_invoke_time` no accept/start
- `client_done_time` + `client_duration_ms` no `session_end` / error / timeout

`meta` do evento Hub `tools_call` (agent__*) inclui `loom_session_id` + `loom_invocation_id`.

### 3.3 Fase C — Tool spans do agent-runtime (extension + FK Core)

Tabela (pode viver em `mcp_hub` ou Core com ok):

```text
invocation_tool_spans
  invocation_id, server_name, tool_name, started_at, duration_ms,
  ok|error, error_code
```

Emitidos no loop do agent-runtime (ou BFF ao proxy MCP). Permite FinOps
“custo do agent X impulsionado por tool Y” e uso ADO real por client.

### 3.4 Fase D — Agregados / FinOps views (read models)

Views SQL ou tabelas rollup diárias (job simples):

- `hub_usage_daily(slug, day, lists, calls, denials, agent_starts, p95_ms)`
- `hub_finops_daily(slug, agent_id, day, invocations, input_tokens, output_tokens, estimated_cost, runtime_ms)`

Fonte: events A + invocations B + spans C + colunas cost já existentes.

## 4. Visões (produto → dado)

### Uso

| Visão | Query mínima |
|-------|----------------|
| Tráfego por client | events group by slug |
| Top tools | tools_call ok by tool_name |
| Denials | phase=denied by slug/group/tool |
| Latência p95 list/call | duration_ms percentiles |
| Agents via Hub | tools_call name like agent__% + joins invocations |

### Adesão

| Visão | Query mínima |
|-------|----------------|
| Clients vivos | last_seen + events 7d |
| Funil | distinct sessions: initialize → list → call → agent__ |
| Agents enabled vs usados | clients.agents_enabled vs calls agent__ |
| Grants vs uso | grants JSONB vs distinct server_id/tool em calls |
| Perfis ativos | idp_groups nas events |

### FinOps

| Visão | Query mínima |
|-------|----------------|
| Custo por client | invocations.mcp_client_slug × estimated_cost / tokens |
| Custo por agent | group by agent_id |
| Custo por subject_hash | (privacy-aware; admin only) |
| Orphans / waste | status pending/streaming > N min (create_task) |
| Custo por tool interna | spans × rate card opcional (fase C+) |

**Nota FinOps local:** agent-runtime + LiteLLM → tokens em invocation quando
o runtime/BFF já popular `input_tokens`/`output_tokens`. Garantir esse
preenchimento no path Hub (hoje pode estar vazio) é parte da Fase B.

## 5. Pontos de instrumentação

```text
mcp-hub http_app / use_cases/tools
  initialize     → já upsert client; + event initialize; last_seen
  tools/list     → event + last_seen + tool_count/server_count
  tools/call     → event start/end + phase + duration; last_seen
  admin patch/grants → event admin_*

BFF mcp_hub_agents (Core — ok Dev)
  start_agent_run → source/slug/hub_session/wait + timing start
  _consume_local_stream end → timing done + tokens se disponíveis
  tools_call meta ← loom ids (Hub já pode receber no result)

agent-runtime invoke loop (Extension)
  cada MCP tools/call → span (Fase C)
```

Writer: port `TelemetryStore` no mcp-hub (hexagonal); adapter PG.
Falhas de write **não** falham o JSON-RPC (log warning).

## 6. API / UI (depois dos dados)

**Extension plugin — aba Analytics (ou seção em Local Runtime):**

1. Overview clients (ativos, calls 24h, denials)
2. Tool explorer (top + deny)
3. Agents Hub (runs, complete rate, duration)
4. FinOps strip (custo 7/30d por client) — se tokens/cost populados

**BFF read APIs** (extension proxy → hub ou Core read-only):

```text
GET /api/mcp/hub/analytics/summary?from=&to=
GET /api/mcp/hub/analytics/tools?slug=
GET /api/mcp/hub/analytics/agents?slug=
GET /api/mcp/hub/analytics/finops?from=&to=   # agrega Core invocations
```

Escopos: `mcp:read` / `settings:read` (definir na spec); sem PII em claro.

## 7. Fases de entrega

| Fase | Entrega | Zona | Critério de aceite | Status |
|------|---------|------|--------------------|--------|
| **A0** | Spec detalhada (DDL + campos meta + privacy) | Docs | Spec merged; Dev ok Core B | **done** |
| **A1** | `hub_telemetry_events` + last_seen em list/call + writer Hub | Extension | Smoke: 1 list + 1 call → 2 rows; deny gravado | **done** |
| **A2** | APIs summary/tools (read) + UI mínima Overview | Ext + BFF fino | Plugin mostra calls 24h por slug | **done** |
| **B1** | Colunas source/slug/hub_session/wait + timings Hub invoke | **Core** (ok Dev) | Invocation Hub queryável por slug; duration preenchida | **done** |
| **B2** | Tokens/cost no path local Hub (se faltando) | Core / runtime | finops via session_end + BFF join | **done** |
| **C1** | Tool spans agent-runtime | Extension (+ FK) | SSE `tool_span` → `invocation_tool_spans` | **done** |
| **D1** | Rollups diários + UI FinOps / adesão funil | Ext | Summary 24h/7d/30d + FinOps no plugin | **done** (v1; job diário opcional depois) |

Ordem recomendada: **A0 → A1 → B1 → A2 → B2 → C1 → D1** (concluída baseline 2026-09-14).

## 8. Gates / não fazer no v1

- Kafka / Rabbit (ver discussão create_task; job PG depois se precisar resiliência de *execução*, separado de telemetria).
- Logar `arguments` / prompt / response no event stream.
- APM novo (Datadog obrigatório) — PG + logger bastam local.
- Refatorar audit_* do frontend admin como substituto — útil complementar, não cobre Hub JSON-RPC.

## 9. Estimativa grosseira

| Fase | Esforço relativo |
|------|------------------|
| A0 docs | 0.5 d |
| A1 | 1–2 d |
| A2 | 1–2 d |
| B1+B2 | 1–2 d (Core) |
| C1 | 1–2 d |
| D1 | 1–2 d |

## 10. Próximo passo imediato

Baseline A–D implementada (2026-09-14). Follow-ups opcionais: job de rollup diário
persistido; retenção/TTL de events; smoke E2E list→call→analytics no compose.
