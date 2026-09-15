# Changelog — divergência do fork vs Loom público

**Upstream:** [awslabs/loom](https://github.com/awslabs/loom) (`upstream/main`)  
**Fork:** [jsmesquita/loom-ext](https://github.com/jsmesquita/loom-ext)  
**Objetivo:** registrar **tudo que toca o core do Loom** versus o que ficou **fora** (`local-runtime/`), para:

1. medir o grau de acoplamento ao upstream;
2. planejar `git fetch upstream` / rebase / merge com conflitos previsíveis;
3. preferir novos ganchos na extension em vez de alargar o core, quando possível.

> **Docs do fork vivem aqui** (`local-runtime/docs/`), não em `docs/` na raiz do
> Loom — assim não concorrem com o upstream no sync. Índice:
> [README.md](README.md).

> Este arquivo **não** substitui o histórico git. É um índice humano, atualizado
> sempre que uma mudança entrar em `backend/`, `frontend/` (fora do plugin),
> `docker-compose.yml`, `makefile` da raiz, ou outros paths “Loom puro”.

**Como atualizar:** ao final de cada entrega, acrescente uma entrada em
[Registro](#registro) (mais recente no topo). Marque a coluna **Zona**.

| Zona | Significado | Risco no pull do upstream |
|------|-------------|---------------------------|
| **Core** | Código/plataforma Loom (`backend/`, `frontend/` host, compose raiz, makefile raiz) | Alto — pode conflitar com awslabs/loom |
| **Extension** | `local-runtime/**` (plugin UI, sidecars, templates, overlay) | Baixo — upstream não tem esse tree |
| **Docs** | `local-runtime/docs/**` (ADRs, specs, guias, este changelog) | Baixo — fora do Loom; raiz `docs/` do fork removida |
| **Config** | `etc/docker/**`, `.env.example`, realm Keycloak, LiteLLM local | Médio — stack local do fork |

**Baseline de comparação:** `main` do fork (`origin/main`).  
**Branch de planejamento (refactor guidelines):** `plan/local-runtime-guideline-refactor`.

**Instruções de agentes:** hub [`README.md`](README.md) → [`guide/rules.md`](guide/rules.md) →
guias em [`guide/`](guide/). Pointers: Cursor
`.cursor/rules/prefer-local-runtime-extension.mdc`; Claude `CLAUDE.md`.

---

## Resumo rápido (grau de alteração)

| Área | Situação no fork | Notas para rebase |
|------|------------------|-------------------|
| IdP ACL (`backend/app/idp/`, auth, settings IdP) | **Core** grande | Conflitos prováveis em `auth.py`, `main.py`, routers |
| MCP catalog | **Core** alinhado upstream (sse / streamable_http) | Sem stdio/`MCP_RUNTIME_URL`; hosts na extension ([ADR 0014](adr/0014-mcp-host-isolated-http-registration.md)) |
| Invoke local / Orientador / LiteLLM | **Core** (`local_invoke`, `local_agents`) + LiteLLM em `etc/` + agent-runtime na extension | `invocations.py` / `local_invoke.py` sensíveis |
| Extension Host UI | **Core** fino (`frontend/src/extensions/*`, `App.tsx`, vite alias) | Manter host estável (ADR 0006) |
| Hub MCP (OAuth, clients, agents-as-tools) | **Core** BFF fino (`/info` + ext proxy) + **Extension** sidecar `mcp-hub` + plugin | Data-plane no Hub (ADR 0015); telemetria Spec 028 em DB `mcp_hub` |
| Model Configuration (Agent Detail) | **Core** UI (`AgentDetailPage`, `DeploymentPanel`, `api/agents.ts`) | Merge Bedrock+LiteLLM no cliente — ver entrada 2026-09-14 |
| Docs do fork | **Docs** em `local-runtime/docs/` (ADRs, specs, guias) | Baixo — sem `docs/` na raiz |

**Regra de ouro (ADR 0006):** feature nova → `local-runtime/`. Docs novas → `local-runtime/docs/`. Core só sem alternativa (BFF, Extension Host, auth, catalog).

---

## Como usar ao puxar o Loom público

```bash
git fetch upstream
git checkout main
git merge upstream/main   # ou rebase da feature em cima
```

1. Abra este changelog e filtre entradas **Core**.
2. Para cada arquivo Core listado, rode `git log upstream/main -- <path>` e compare com o nosso diff.
3. Conflitos em **Extension** / `local-runtime/docs` costumam ser triviais ou inexistentes.
4. Depois do merge, acrescente uma entrada “sync upstream” com a data e o SHA de `upstream/main`.

Checklist pós-merge:

- [ ] `backend` sobe; testes IdP / MCP hub / local_invoke
- [ ] `frontend` build; Extension Host ainda carrega `@loom-ext/local-runtime`
- [ ] overlay `local-runtime/compose/overlay.yml` aplica sem quebrar serviços novos do upstream
- [ ] atualizar este arquivo se o sync tocou Core

---

## Registro

### 2026-09-15 — ADR 0015 fase 5: remover data-plane Hub do Core

| | |
|--|--|
| **Zona** | **Core** + Docs |
| **Ok Dev** | Sim — limpeza pós-validação Cursor/Hub |
| **Motivo** | Hub já materializa/call via JWT user + upstream; Core não deve conhecer o data-plane Hub |
| **Removido** | Rotas `/api/mcp/hub/materialize*` / `tools/call` / `agents/*`; `mcp_hub_agents.py`; helpers materialize/call em `mcp_hub.py` |
| **Mantido** | `GET /api/mcp/hub/info`; `/api/ext/local-runtime/*` + `mcp_hub_proxy` (ops/plugin; service token Hub↔BFF) |
| **Docs** | ADR 0015 Aceito; architecture L2/L3; Hub README |

### 2026-09-15 — ADR 0015 parcial: Hub data-plane sem `/api/mcp/hub`

| | |
|--|--|
| **Zona** | **Extension** (`mcp-hub`) + Keycloak realm mapper |
| **Ok Dev** | Sim — implementar, sem commit até teste |
| **Hub** | Catálogo Loom ∩ grants; `tools/call` upstream; agents via `/api/agents` + SSE |
| **Auth** | Dual-aud interim (`loom-mcp-hub` + `loom-frontend`); exchange opcional via env |
| **Core** | Rotas `/api/mcp/hub/*` ainda existem (não usadas no data-plane Hub); remover após validação |

### 2026-09-15 — ADR 0015 rascunho: Hub como cliente Loom

| | |
|--|--|
| **Zona** | **Docs** |
| **Ok Dev** | Sim (rascunho) |
| **Docs** | [ADR 0015](adr/0015-mcp-hub-as-loom-api-client.md) — norte syncável; Core sem `/api/mcp/hub` |

### 2026-09-15 — Varredura: resíduos mcp-runtime no Core

| | |
|--|--|
| **Zona** | Core + fork sob `backend/` |
| **Removido** | enrich `MCP_RUNTIME_TOKEN` / `service_bearer`; guard `stdio` no Hub; comentários compose |
| **Já deleted** | `mcp_runtime_client.py`, `mcp_templates.py`, `test_mcp_runtime.py` |
| **Mantido (fork)** | `db.py` DROP colunas stdio legadas; BYO/`local_invoke`/Hub (não são mcp-runtime) |

### 2026-09-15 — mcp-* lateral trust (sem bearer; Core intacto)

| | |
|--|--|
| **Zona** | **Extension** (`mcp-runtime` HTTP) |
| **Ok Dev** | Sim |
| **Motivo** | Evitar patch Core para Refresh Tools; rede Docker / loopback é a fronteira |
| **Fix** | Auth off por default; opt-in `MCP_RUNTIME_REQUIRE_AUTH=1` |
| **Core** | Revertido inject de `MCP_RUNTIME_TOKEN` em `services/mcp.py` |

### 2026-09-15 — Docs: architecture + specs alinhados a ADR 0014

| | |
|--|--|
| **Zona** | **Docs** |
| **Ok Dev** | Sim |
| **Docs** | `architecture.md` L2/dados; ADR 0004 superseded; specs 006–016/015/011/012/014; índices |

### 2026-09-15 — Limpeza residual stdio / hosted / auth loom

| | |
|--|--|
| **Zona** | **Core** + **Extension** + **Docs** |
| **Ok Dev** | Sim — “Pode seguir” nos residuais |
| **Core** | Sem `mcp_runtime_client`; sem branches stdio/loom; Hub tool call só HTTP |
| **Extension** | mcp-runtime só `TEMPLATE=` + `/mcp` (removidos hosted `/h` `/s` register API) |
| **Plugin** | Label MCP sem `template_id` |

### 2026-09-15 — Remoção residual do mint Hub (`mcp_hub_sessions`)

| | |
|--|--|
| **Zona** | **Core** + **Docs** |
| **Ok Dev** | Sim — limpar mint |
| **Core** | Removidos model/funções/rotas mint; `DROP TABLE mcp_hub_sessions` |
| **Docs** | architecture L4 |
| **Mantido** | rejeição `hs_…` no sidecar oauth (fail-closed) |

### 2026-09-15 — Loom sem mcp-runtime (só formulário HTTP)

| | |
|--|--|
| **Zona** | **Core** + **Extension** + **Docs** |
| **Ok Dev** | Sim — “Loom deixa de conhecer o mcp-runtime” / limpar modelo |
| **Core** | Sem stdio/templates/`MCP_RUNTIME_URL`; DROP `mcp_servers.template_*` / `secret_refs` / `runtime_state`; stub `ensure_stdio_ready` só p/ import Hub |
| **Extension** | Overlay: só `mcp-*` com `TEMPLATE=` |
| **Docs** | ADR 0014, guia registro, architecture L2/L4 |
| **Fora de escopo** | mcp-hub features (só `server_slug` usa `name`) |

### 2026-09-15 — ADR 0014 v2: TEMPLATE= / serviço por MCP

| | |
|--|--|
| **Zona** | **Extension** + **Docs** |
| **Ok Dev** | Sim — desenho TEMPLATE= + `/mcp` |
| **Extension** | `TEMPLATE` → boot single + `POST /mcp`; overlay: `mcp-azure-devops`, `mcp-rancher`, `mcp-grafana` |
| **Docs** | ADR 0014, guia `mcp-host-http-registration.md` |
| **Core** | (superseded pela entrada acima) |

### 2026-09-15 — ADR 0014: MCP host isolado (hosted HTTP)

| | |
|--|--|
| **Zona** | **Extension** + **Docs** |
| **Ok Dev** | Sim — “Loom o mais isolado possível” |
| **Extension** | `mcp-runtime` `hosted/servers.yaml`, boot auto, `GET /hosted`, `/h/{slug}/mcp` (legado all-in-one) |
| **Docs** | ADR 0014, guia `mcp-host-http-registration.md`; backlog REF-2026-09-15-01 (remover stdio Core) |
| **Core** | Sem remoção nesta fase — path stdio legado permanece |

### 2026-09-15 — Rename `source=local` → `source=external` (UI: BYO agent)

| | |
|--|--|
| **Zona** | **Core** + **Docs** |
| **Ok Dev** | Sim — rename solicitado |
| **Motivo** | “local” sugeria só laptop; valor canônico = fora do AgentCore |
| **Core** | `agents.source`: `local`→`external`; seed/create; `is_external_agent()` (+ alias `is_local_agent`); migração em `init_db`; UI badge/label **BYO** |
| **Compat** | Predicate ainda aceita `local` legado até a migração rodar |
| **Docs** | architecture + ADR 0005 nota; este changelog |

### 2026-09-15 — HITL approval policies no caminho local (agent-runtime)

| | |
|--|--|
| **Zona** | **Core** + **Extension** |
| **Ok Dev** | Sim — fix do gate que não acionava no Chat `source=local` |
| **Motivo** | `local_invoke` enviava `approval_policies: []`; runtime não fazia loop_hook |
| **Core** | `backend/app/services/local_invoke.py`, `backend/app/routers/invocations.py` — repassa policies ativas; BFF trata SSE `approval_needed` → `approval_request` / decide → POST runtime |
| **Extension** | `agent-runtime` — match loop_hook antes de MCP tool; `POST .../approval-decision`; store `arm/wait/resolve_approval` |
| **Limite** | Gate cobre **tools MCP** no agent-runtime. Tools A2A (ADK) ainda não rodam neste runtime. |
| **Sync** | Baixo risco funcional; conflito possível em `local_invoke.py` / `invocations.py` no rebase |

### 2026-09-14 — Hub analytics Errors tab

| Zona | Path | Nota |
|------|------|------|
| **Extension** | mcp-hub `analytics_errors` + plugin Errors tab | Recent `phase=error\|denied` + rollup `error_code` (sem payload) |
| **Core** | BFF `/analytics/errors` proxy | `mcp:read` |
| **Docs** | Spec 028 | Endpoint + critério UI |

### 2026-09-14 — Hub analytics Operate nav (tabs)

**Motivo Core:** host `App.tsx` só renderizava extensions em Build; Operate precisa
do mesmo loop para o item `hub-analytics`.

| Zona | Path | Nota |
|------|------|------|
| **Core** | `frontend/src/App.tsx` | Render extensions `nav.section === "operate"` |
| **Extension** | plugin `register` + `HubAnalyticsPage` | Menu Operate; tabs Overview / Tools / Adoption / FinOps (EN) |
| **Docs** | overview, development, CHANGELOG | Nav Operate + Spec 028 UI |

### 2026-09-14 — Telemetria MCP Clients (uso / adesão / FinOps)

**Motivo Core:** atribuição Hub→invocation (`source`/`mcp_client_slug`/`hub_session_id`/`wait_mode`),
timings/tokens a partir de SSE, tabela `invocation_tool_spans`, BFF analytics + join FinOps.
Autorizado pelo Dev (“aplicar tudo”).

| Zona | Path | Nota |
|------|------|------|
| **Docs** | Spec 028, plano REF-10, architecture, CHANGELOG | DDL events, privacy, fases A–D done |
| **Extension** | `mcp-hub` store/ports/tools/http + plugin `HubAnalyticsSection` | `hub_telemetry_events`, last_seen, admin_patch/grants events, analytics APIs, UI 24h/7d/30d |
| **Extension** | `agent-runtime` invoke | SSE `tool_span` por MCP call |
| **Core** | `invocation(s)`, `invocation_tool_spans`, `mcp_hub_agents`, `db` migrate, BFF analytics | attribution + timings/tokens; FinOps join |

### 2026-09-14 — Plano telemetria MCP Clients (uso / adesão / FinOps)

| Zona | Path | Nota |
|------|------|------|
| **Docs** | `backlog/mcp-hub-telemetry-analytics-plan.md`, `backlog/refactoring.md` (REF-10) | Events Hub, last_seen, ligação invocations, spans, rollups; Core B1 com gate |

### 2026-09-14 — Local agents: MCP/A2A persistidos + limits + Hub ∩ grants

| Zona | Path | Nota |
|------|------|------|
| **Core** | `backend` `local_agent_mcp.py`, `local_agents.py`, `local_invoke.py`, `mcp_hub*`, `invocations.py`, `agents.py` | Links MCP/A2A + `options` no config; Hub invoke passa grants; Chat fallback aos MCPs linkados; AgentResponse expõe ids/limits |
| **Core** | `frontend` create + Detail | Allowed models, MCP, A2A, timeout / max_tool_rounds; Detail: Save integrations |
| **Extension** | `mcp-hub` ports / loom_http / tools | `agents_invoke` envia `hub_server_ids` + `hub_tool_allowlists` |

### 2026-09-14 — Local agents: tag profile + model no create/Detail

| Zona | Path | Nota |
|------|------|------|
| **Core** | `backend/app/routers/local_agents.py` | Create aceita `model_id` / `allowed_model_ids` (+ `tags` já previsto) |
| **Core** | `backend/app/routers/agents.py` | `PATCH /api/agents/{id}` aceita `tags`; validação de model relaxada para `source=local`; sync `allowed_model_ids` no `AGENT_CONFIG_JSON` |
| **Core** | `frontend` `LocalAgentCreateForm`, `AgentListPage`, `AgentDetailPage`, `App`, `api/agents`, `hooks/useAgents` | Create: seletor LiteLLM + `ResourceTagFields`; Detail local: Model Configuration + Save tag profile |

### 2026-09-14 — A2: create/edit local agents from templates

| Zona | Path | Nota |
|------|------|------|
| **Core** | `backend/app/routers/local_agents.py`, `services/local_agent_templates.py`, `main.py` | Ok Dev: BFF create/list/behavior; proxy materialize no agent-runtime |
| **Core** | `frontend` Agents Local tab + Detail behavior | Create com `params.objective`; reset to template |
| **Extension** | `templates/assistente-local.yaml` | Template genérico (substitui exemplo guia-biblioteca) |

### 2026-09-14 — A1: agent templates loader

| Zona | Path | Nota |
|------|------|------|
| **Extension** | `services/agent-runtime/templates/`, `domain/agent_template.py`, `adapters/outbound/yaml_agent_templates.py` | Spec 026 allowlist + materialize config |
| **Extension** | compose mount `AGENT_TEMPLATES_DIR`, Dockerfile `COPY templates` | |

### 2026-09-14 — ADR 0013 + specs 026/027 (templates + worker pool)

| Zona | Path | Nota |
|------|------|------|
| **Docs** | `adr/0013-…`, `specs/026-…`, `specs/027-…` | Agents locais por template; pool agnóstico; dual path AgentCore; K8s-ready |
| **Docs** | `architecture.md`, índices ADR/specs | Ponteiros ao desenho |

### 2026-09-14 — agent-runtime: 2 réplicas no compose (pool)

| Zona | Path | Nota |
|------|------|------|
| **Extension** | `compose/overlay.yml`, `makefile` | Pool de workers: sem porta no host; `make local.up` sobe `--scale agent-runtime=2` (`AGENT_RUNTIME_REPLICAS`) |

### 2026-09-14 — agent-runtime SSE fecha conexão após invoke

| Zona | Path | Nota |
|------|------|------|
| **Extension** | `services/agent-runtime/.../adapters/inbound/http_app.py` | `/v1/invoke` SSE: `Connection: close` + `close_connection=True` para o BFF/Hub não ficarem em `streaming` após `session_end` |

### 2026-09-14 — mcp-runtime owns templates/

| Campo | Valor |
|-------|--------|
| **Zona** | **Extension** (+ comentário **Core** path sync) |
| **Motivação** | Allowlist YAML é do supervisor stdio — não asset compartilhado na raiz de `local-runtime/` |
| **Core** | `backend/app/services/mcp_templates.py` — comentário de sync → novo path (sem lógica) |
| **Extension** | `services/mcp-runtime/templates/*.yaml`; compose mount; Dockerfile `COPY templates`; default `templates_dir()` |
| **Docs** | architecture, rules, overview, ADR 0004/0006, READMEs |
| **Risco sync** | Baixo |

### 2026-09-14 — cursor-adapter hexagonal (REF-05)

**Contexto:** isolar translation/planner do SDK Cursor.

| Zona | Paths | O que mudou |
|------|-------|-------------|
| **Extension** | `services/cursor-adapter/cursor_adapter/{domain,application,adapters}/` | Ports + use case chat |
| **Docs** | backlog REF-05 done | |

**Impacto no sync upstream:** baixo.

---

### 2026-09-14 — mcp-runtime hexagonal leve (REF-04)

**Contexto:** alinhar supervisor stdio ao layout ports/adapters.

| Zona | Paths | O que mudou |
|------|-------|-------------|
| **Extension** | `services/mcp-runtime/mcp_runtime/{domain,application,adapters}/` | ProcessSupervisor + outbound YAML/stdio/secrets |
| **Docs** | backlog REF-04 done | |

**Impacto no sync upstream:** baixo.

---

### 2026-09-14 — agent-runtime hexagonal (REF-03)

**Contexto:** mesma disciplina do Hub — domain/application/adapters.

| Zona | Paths | O que mudou |
|------|-------|-------------|
| **Extension** | `services/agent-runtime/agent_runtime/{domain,application,adapters}/` | Ports LLM/MCP/Session + use case invoke |
| **Docs** | backlog REF-03 done, plano Fase 3 | |

**Impacto no sync upstream:** baixo.

---

### 2026-09-14 — Hub store Postgres (REF-01)

**Contexto:** paridade produção; port `HubStore` + DB dedicado.

| Zona | Paths | O que mudou |
|------|-------|-------------|
| **Extension** | `mcp_hub/adapters/outbound/pg_store.py`, `wiring.py` | `PostgresHubStore` + migrate JSON |
| **Config** | `compose/overlay.yml`, `postgres-init/02-mcp-hub-db.sql`, `.env.example` | DSN `mcp_hub` |
| **Docs** | architecture, backlog REF-01/02 done | |

**Impacto no sync upstream:** baixo (init SQL sob `etc/docker/`).

---

### 2026-09-14 — mcp-hub hexagonal strangler (REF-02)

**Contexto:** decisões do plano aceitas; primeira fatia de layout ports/adapters.

| Zona | Paths | O que mudou |
|------|-------|-------------|
| **Extension** | `services/mcp-hub/mcp_hub/{domain,application,adapters}/` | Layout hexagonal + ports + FileHubStore/Loom/OAuth classes |
| **Extension** | `application/use_cases/{session_allowlist,tools}.py` | Use cases + DI em `serve()` / `HubHandler` |
| **Extension** | shims `access.py`…`http_app.py` | Compat de imports |
| **Docs** | plano / backlog REF-02 | Fase 1 itens 1–8 |

**Impacto no sync upstream:** baixo.

---

### 2026-09-14 — Plano de refactor local-runtime × guidelines

**Contexto:** iniciar planejamento (sem código) para aderência hexagonal / SOLID.

| Zona | Paths | O que mudou |
|------|-------|-------------|
| **Docs** | `backlog/local-runtime-guideline-refactor-plan.md` | Plano fasado 0–6 |
| **Docs** | `backlog/refactoring.md` | REF-02…06 |
| **Docs** | `README.md`, este changelog | Links / baseline fork |

**Impacto no sync upstream:** baixo.

---

### 2026-09-14 — Guia Python best practices (hexagonal alvo)

**Contexto:** documentar SOLID/Calisthenics/KISS/YAGNI/DRY/Clean Code/GoF e
estrutura hexagonal para sidecars — **sem** refatorar código existente.

| Zona | Paths | O que mudou |
|------|-------|-------------|
| **Docs** | `local-runtime/docs/guide/python-best-practices.md` | Guia canônico |
| **Docs** | `local-runtime/docs/README.md`, `guide/development.md` | Links |

**Impacto no sync upstream:** baixo.

---

### 2026-09-14 — Regras: Core só com autorização do Dev

**Contexto:** reforçar gate humano antes de qualquer exceção no Loom.

| Zona | Paths | O que mudou |
|------|-------|-------------|
| **Docs** | `local-runtime/docs/guide/rules.md` | Features em local-runtime; Core = exceção + ok explícito do Dev |
| **Extension** | `CLAUDE.md`, `.cursor/rules/…` | Lembrete do hard gate (sem duplicar política) |

**Impacto no sync upstream:** baixo.

---

### 2026-09-14 — architecture: Mermaid portátil + endpoints via env

**Contexto:** C4 plugin não renderiza em vários previews; arquitetura alinhada a prod (config).

| Zona | Paths | O que mudou |
|------|-------|-------------|
| **Docs** | `guide/architecture.md` | L1–L3 em `flowchart`; tabela env; sem portas como contrato |
| **Docs** | `guide/rules.md` | Manutenção: Mermaid portátil + env |

**Impacto no sync upstream:** baixo.

---

### 2026-09-14 — architecture.md: dados Core vs Fork vs local-runtime

**Contexto:** deixar explícito o que é schema upstream, extensão PG do fork e stores da extension.

| Zona | Paths | O que mudou |
|------|-------|-------------|
| **Docs** | `local-runtime/docs/guide/architecture.md` | Seções 1–4 do modelo de dados |
| **Docs** | `guide/rules.md` | Manutenção exige tag de origem do store |

**Impacto no sync upstream:** baixo.

---

### 2026-09-14 — Guia scalability / reliability

**Contexto:** NFRs de escala, HA, falha e idempotência filtrados ao fork (não em `rules.md`).

| Zona | Paths | O que mudou |
|------|-------|-------------|
| **Docs** | `local-runtime/docs/guide/scalability-reliability.md` | Guia NFR |
| **Docs** | `rules.md`, `architecture.md`, `README.md` | Links |

**Impacto no sync upstream:** baixo.

---

### 2026-09-14 — Arquitetura C4 + regra de atualização

**Contexto:** documentar L1/L2/L3 e modelo de dados; obrigar sync do doc em mudanças.

| Zona | Paths | O que mudou |
|------|-------|-------------|
| **Docs** | `local-runtime/docs/guide/architecture.md` | C4 + ER Postgres/JSON Hub |
| **Docs** | `guide/rules.md` | § Manutenção da arquitetura + checklist |
| **Docs** | README, CLAUDE, Cursor pointer | Links |

**Impacto no sync upstream:** baixo.

---

### 2026-09-14 — Guia de segurança (OWASP/RFC filtrados)

**Contexto:** checklist objetivo para API/web/sidecars deste fork — sem inflar.

| Zona | Paths | O que mudou |
|------|-------|-------------|
| **Docs** | `local-runtime/docs/guide/security.md` | Top 10 mapeado, RFCs OAuth/JWT, PII, injection, checklist |
| **Docs** | `README.md`, `guide/development.md` | Links |

**Impacto no sync upstream:** baixo.

---

### 2026-09-14 — Regra: sem refactor sem pedido + backlog

**Contexto:** oportunidades de melhoria registradas; atuação só sob demanda do Dev.

| Zona | Paths | O que mudou |
|------|-------|-------------|
| **Docs** | `local-runtime/docs/guide/rules.md` | § Não refatorar sem pedido do Dev |
| **Docs** | `local-runtime/docs/backlog/refactoring.md` | Template + lista de itens |
| **Docs** | README, python-best-practices, pointers IDE | Links |

**Impacto no sync upstream:** baixo.

---

### 2026-09-14 — `rules.md` (rename lowercase)

**Contexto:** alinhar ao padrão kebab/lowercase dos outros guias.

| Zona | Paths | O que mudou |
|------|-------|-------------|
| **Docs** | `local-runtime/docs/guide/rules.md` | Renomeado de `RULES.md` |
| **Docs** / pointers | README, CLAUDE, Cursor, guias | Links atualizados |

**Impacto no sync upstream:** baixo.

---

### 2026-09-14 — `RULES.md` sob `guide/`

**Contexto:** regras junto dos guias operacionais.

| Zona | Paths | O que mudou |
|------|-------|-------------|
| **Docs** | `local-runtime/docs/guide/RULES.md` | Movido de `local-runtime/docs/RULES.md` |
| **Docs** / pointers | README, CLAUDE, Cursor rule, changelog | Paths atualizados |

**Impacto no sync upstream:** baixo.

---

### 2026-09-14 — Migração ADRs/specs para `local-runtime/docs/`

**Contexto:** cumprir a política de docs só na extension; remover concorrência com `docs/` do Loom.

| Zona | Paths | O que mudou |
|------|-------|-------------|
| **Docs** | `local-runtime/docs/adr/*`, `local-runtime/docs/specs/*` | ADRs 0001–0012 e specs 001–025 movidos da raiz |
| **Docs** | `docs/adr`, `docs/specs` (raiz) | Removidos |
| **Docs** | índices `adr/README`, `specs/README`, guias, RULES, changelog | Links atualizados |

**Impacto no sync upstream:** baixo (add-only sob local-runtime; delete de paths que o upstream não tinha).

---

### 2026-09-14 — Guias de uso em `local-runtime/docs/guide/`

**Contexto:** padronizar how-to do repo fora do Loom; Claude/Cursor só apontam.

| Zona | Paths | O que mudou |
|------|-------|-------------|
| **Docs** | `local-runtime/docs/guide/{overview,getting-started,development,upstream-sync,mcp-hub}.md` | Guias de uso |
| **Docs** | `local-runtime/docs/README.md` | Hub de documentação |
| **Extension** | `local-runtime/README.md`, `CLAUDE.md`, `.cursor/rules/…` | Pointers; conteúdo operacional removido de CLAUDE |

**Impacto no sync upstream:** baixo.

---

### 2026-09-14 — Regras canônicas em `RULES.md` (pointers IDE)

**Contexto:** uma única fonte de regras, agnóstica de Cursor/Claude; arquivos de IDE só apontam.

| Zona | Paths | O que mudou |
|------|-------|-------------|
| **Docs** | `local-runtime/docs/guide/RULES.md` | Política de colocação Core vs extension (canônica) |
| **Docs** | `local-runtime/docs/README.md`, `CHANGELOG-LOOM-FORK.md` | Índice + refs |
| **Extension** | `.cursor/rules/prefer-local-runtime-extension.mdc`, `CLAUDE.md` | Pointers finos (sem duplicar corpo) |

**Impacto no sync upstream:** baixo.

---

### 2026-09-14 — Docs do fork sob `local-runtime/docs/`

**Contexto:** evitar concorrência com `docs/` do Loom no sync upstream.

| Zona | Paths | O que mudou |
|------|-------|-------------|
| **Docs** | `local-runtime/docs/CHANGELOG-LOOM-FORK.md` | Changelog movido de `docs/` (raiz) |
| **Docs** | `local-runtime/docs/README.md`, `adr/README.md` | Política + índice; legado apontado na raiz |
| **Extension** | `.cursor/rules/prefer-local-runtime-extension.mdc`, `CLAUDE.md` | Docs só em local-runtime; path do changelog atualizado |

**Impacto no sync upstream:** baixo.

---

### 2026-09-14 — Agents as MCP tools (implementação) + Model Configuration LiteLLM

**Contexto:** Fase 2 do Hub (ADR 0012 / spec 025): expor agents Loom como tools MCP; UI Local runtime `agents_enabled`; correção do editor de models para catálogo LiteLLM; bypass agent-runtime para mocks LiteLLM.

| Zona | Paths | O que mudou |
|------|-------|-------------|
| **Core** | `backend/app/routers/mcp_hub.py` | Endpoints Hub: `materialize-agents`, `agents/invoke`, `agents/runs/{id}` |
| **Core** | `backend/app/services/mcp_hub_agents.py` *(novo, WIP)* | Materialize RBAC, invoke async/sync, status/result |
| **Core** | `backend/app/services/local_invoke.py` | Mocks `orientador-academico` / `mock-echo` **não** passam pelo agent-runtime (evita hang) |
| **Core** | `backend/tests/test_mcp_hub.py`, `test_local_invoke.py` | Cobertura materialize/RBAC e path agent-runtime com model não-mock |
| **Core** | `frontend/src/api/agents.ts` | `fetchAllModelOptions()` = Bedrock + LiteLLM |
| **Core** | `frontend/src/pages/AgentDetailPage.tsx` | Model Configuration usa catálogo mesclado (+ fallback dos ids do agente) |
| **Core** | `frontend/src/components/DeploymentPanel.tsx` | Idem para Allowed Models |
| **Extension** | `local-runtime/services/mcp-hub/mcp_hub/{http_app,loom_client,store}.py` | `agents_enabled`; `tools/list`/`tools/call` para `agent__*` / status / result |
| **Extension** | `local-runtime/services/mcp-hub/tests/test_store_identity.py` | Flag `agents_enabled` |
| **Extension** | `local-runtime/plugin/src/pages/LocalRuntimePage.tsx` | Toggle “Expose Loom agents” independente de perfil IdP |

**Por que Core (não só extension):** o Hub precisa de BFF autenticado no FastAPI do Loom (materialize/invoke com sessão/RBAC). O editor de models é página Agent Detail do host — o Extension Host **não** injeta nesse card.

**Alternativa rejeitada:** unificar LiteLLM em `GET /api/agents/models` (quebraria o split Bedrock vs `/models/litellm`).

**Estado:** código Hub agents + UI models em working tree / imagem local; ADRs/specs da Fase 2 ainda sob `docs/` na raiz (legado — migrar depois).

---

### 2026-09-13 — MCP Hub OAuth IdP (sem mint) + clients / profile grants

| Zona | Paths (principais) | O que mudou |
|------|--------------------|-------------|
| **Core** | `backend/app/routers/mcp_hub.py`, `services/mcp_hub.py`, `mcp_hub_proxy.py`, `models/mcp_hub.py` | BFF Hub: clients, grants, materialize allowlist; remoção do fluxo mint |
| **Core** | `backend/tests/test_mcp_hub.py` | Contratos Hub |
| **Extension** | `local-runtime/services/mcp-hub/**` | Sidecar OAuth PRM/PKCE, store de clients, proxy tools |
| **Extension** | `local-runtime/plugin/.../LocalRuntimePage.tsx` | Admin de canais + grants por perfil |
| **Docs** | ADR 0007–0011, specs 016–024 | Contrato Hub, OAuth, grants *(hoje em `local-runtime/docs/`)* |

**Risco upstream:** routers/services novos no backend — merge costuma ser add; cuidado se awslabs criar `mcp_hub` com outro desenho.

---

### 2026-09-12…13 — Local agent-runtime, cursor-local, Orientador

| Zona | Paths (principais) | O que mudou |
|------|--------------------|-------------|
| **Core** | `backend/app/services/local_invoke.py`, `local_agents.py`, `routers/invocations.py` | `source=local`, proxy agent-runtime / LiteLLM, seed Orientador |
| **Core** | testes `test_local_invoke.py` | |
| **Extension** | `local-runtime/services/agent-runtime/**`, `cursor-adapter/**` | Data plane invoke + adapter Cursor |
| **Config** | `etc/docker/litellm/config.yaml`, `cursor_handler.py` | Models mock + cursor-local |
| **Docs** | ADR 0005, specs 011–014 | *(hoje em `local-runtime/docs/`)* |

---

### 2026-09 — Local MCP runtime, stdio catalog, Grafana/Rancher

| Zona | Paths (principais) | O que mudou |
|------|--------------------|-------------|
| **Core** | `backend/.../mcp.py`, `mcp_access.py`, `mcp_templates.py`, `mcp_runtime_client.py`, forms/pages MCP no frontend | Catalog, access, deploy path para stdio |
| **Extension** | `local-runtime/services/mcp-runtime/**` (incl. `templates/*.yaml`) | Supervisor stdio + templates |
| **Docs** | ADR 0004, specs 005–010, 015 *(legado)* | |

---

### 2026-09 — Extension Host + extração `local-runtime`

| Zona | Paths (principais) | O que mudou |
|------|--------------------|-------------|
| **Core** | `frontend/src/extensions/*`, `App.tsx`, `vite.config.ts` | Host estável `addExtension` |
| **Extension** | `local-runtime/plugin/**`, `compose/overlay.yml`, `makefile` targets | Plugin + stack sidecar |
| **Docs** | ADR 0006 *(legado)* | |

**Manter estável no rebase:** assinatura de `LoomExtensionHost` / `LoomExtensionRegistration`.

---

### 2026-09 — IdP anti-corruption + stack local (Keycloak / Postgres / LiteLLM)

| Zona | Paths (principais) | O que mudou |
|------|--------------------|-------------|
| **Core** | `backend/app/idp/**`, `dependencies/auth.py`, `routers/auth.py`, `identity_providers.py`, `services/oidc.py`, frontend Login/Auth/IdP panel | Abstração multi-IdP |
| **Config** | `docker-compose.yml`, `etc/docker/keycloak/**`, `postgres-init/**`, `.env.example` | Stack local |
| **Docs** | ADR 0001–0003, specs 001–004 *(legado)* | |

**Risco upstream:** **alto** em auth/OIDC — revisar com cuidado a cada sync.

---

## Inventário WIP (não commitado)

Atualizado em **2026-09-14**. Confirmar com `git status` antes de sync.

**Core**

- `backend/app/routers/mcp_hub.py` (agents endpoints)
- `backend/app/services/mcp_hub_agents.py` (untracked)
- `backend/app/services/local_invoke.py` (skip agent-runtime para mocks)
- `backend/tests/test_mcp_hub.py`, `test_local_invoke.py`
- `frontend/src/api/agents.ts`
- `frontend/src/pages/AgentDetailPage.tsx`
- `frontend/src/components/DeploymentPanel.tsx`

**Extension / Docs**

- `local-runtime/plugin/src/pages/LocalRuntimePage.tsx`
- `local-runtime/services/mcp-hub/mcp_hub/{http_app,loom_client,store}.py`
- `local-runtime/services/mcp-hub/tests/test_store_identity.py`
- `local-runtime/docs/**` (changelog + README de política)

---

## Convenção de novas entradas

```markdown
### YYYY-MM-DD — Título curto

**Contexto:** …

| Zona | Paths | O que mudou |
|------|-------|-------------|
| **Core** | … | … |
| **Extension** | … | … |
| **Docs** | local-runtime/docs/… | … |

**Por que Core (se aplicável):** …
**Impacto no sync upstream:** baixo | médio | alto
```

Relacionado: [ADR 0006](adr/0006-local-runtime-extension-repo.md).
