# MCP Hub (uso rápido)

Data plane + ops: `local-runtime/services/mcp-hub` (porta **8790**).  
O Core Loom **não** expõe rotas Hub — o plugin fala com `/v1/*` no Hub
(JWT SPA + CORS). Catálogo MCP genérico continua em `/api/mcp/servers` no BFF.

## Conceitos

| Conceito | Onde | Notas |
|----------|------|--------|
| Canal (MCP client) | Store do Hub | Ex.: `cursor-vscode`; status enabled/disabled |
| Grants por perfil IdP | UI Local runtime → Hub `/v1/clients/…` | Tools de **servers** MCP |
| `agents_enabled` | Canal (não perfil) | Expõe `agent__*` + status/result |
| OAuth IDE | IdP ativo | client estático `loom-mcp-hub` |
| Ops auth | JWT SPA `aud=loom-frontend` | scopes `mcp:read` / `mcp:write` via grupos |

## Operar na UI

1. Nav **Local runtime** (`mcp:read`; escrita com `mcp:write`)
2. Selecione o canal → Channel settings → **Expose Loom agents** (grava na hora)
3. Escolha um **IdP profile** só para editar grants de servers → **Save profile grants**

## IDE (Cursor)

Ver [getting-started.md](getting-started.md#cursor--mcp-hub-resumo). Após mudar
`agents_enabled`, reinicie o MCP para o catálogo incluir `agent__*`.

## Agents locais (ex.: Orientador)

- Seed: agent `source=external` (BYO) no backend
- Hub `agent__*` → `POST /api/agents/{id}/invoke` (JWT dual-aud)
- Mocks LiteLLM (`orientador-academico`, `mock-echo`) para smoke sem Bedrock
