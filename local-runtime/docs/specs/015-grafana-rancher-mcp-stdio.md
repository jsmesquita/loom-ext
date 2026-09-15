# Spec 015 — Grafana e Rancher MCP (hosts locais)

- **Status:** Aceita (local-runtime / ADR 0014)
- **Data:** 2026-09-13
- **Atualizado:** 2026-09-15 — serviços `TEMPLATE=`; registro HTTP no Loom
- **Implementa:** [ADR 0014](../adr/0014-mcp-host-isolated-http-registration.md)
- **Não é** adapter no core. São templates + secrets no overlay.

## 1. Fluxo

```text
Loom (catálogo + ACL)
  → http://mcp-grafana:8787/mcp     TEMPLATE=grafana
  → http://mcp-rancher:8787/mcp     TEMPLATE=rancher
       │
       ├─ Grafana: uvx mcp-grafana → http://grafana.local:8080
       └─ Rancher: npx rancher-mcp-server → http://kind-control-plane:30080
```

## 2. Templates / env

| Serviço | TEMPLATE | Param env | Secret |
|---------|----------|-----------|--------|
| `mcp-grafana` | `grafana` | `GRAFANA_MCP_URL` | `GRAFANA_SERVICE_ACCOUNT_TOKEN` |
| `mcp-rancher` | `rancher` | `RANCHER_MCP_SERVER_URL` | `RANCHER_MCP_RANCHER_TOKEN` |

### URLs Rancher (lab `kind`)

| Onde | URL |
|------|-----|
| Rede Compose + `kind` | `http://kind-control-plane:30080` |
| Browser no host | `http://rancher.local:8080` |

O overlay anexa os serviços `mcp-*` à rede externa `kind`.

## 3. Registro (operador)

1. Kind rodando; secrets no `.env`.
2. `docker compose … up -d --build mcp-rancher mcp-grafana`
3. Loom → MCP → New → `streamable_http` →
   `http://mcp-rancher:8787/mcp` (ou grafana).
4. Refresh tools + `McpServerAccess`.

## 4. Fora de escopo

- `transport=stdio` / templates no formulário Core
- Port-forward `:8443` a partir do container
