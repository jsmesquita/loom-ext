# MCP host isolado — registro HTTP no Loom

Alvo: [ADR 0014](../adr/0014-mcp-host-isolated-http-registration.md).

## Ideia

1. Extensão sobe MCPs (`TEMPLATE=` → `/mcp`).
2. **Loom não conhece mcp-runtime** — só o formulário nativo de MCP HTTP.

## 1. Serviços no overlay

| Serviço | TEMPLATE | URL (rede Docker) | Host (debug) |
|---------|----------|-------------------|--------------|
| `mcp-azure-devops` | `azure-devops` | `http://mcp-azure-devops:8787/mcp` | `127.0.0.1:8788` |
| `mcp-rancher` | `rancher` | `http://mcp-rancher:8787/mcp` | `127.0.0.1:8789` |
| `mcp-grafana` | `grafana` | `http://mcp-grafana:8787/mcp` | `127.0.0.1:8791` |

Env útil: `AZURE_DEVOPS_ORG`, `AZURE_DEVOPS_PAT`, `RANCHER_MCP_*`,
`GRAFANA_*`, `MCP_RUNTIME_TOKEN`.

```bash
docker compose -f docker-compose.yml -f local-runtime/compose/overlay.yml \
  up -d --build mcp-azure-devops mcp-rancher mcp-grafana
```

## 2. Registrar no Loom (formulário nativo)

**Integrations → MCP → Add**:

| Campo | Valor |
|-------|--------|
| transport | `streamable_http` |
| endpoint_url | `http://mcp-azure-devops:8787/mcp` (ou rancher/grafana) |
| auth | `none` (hosts `mcp-*` confiam na rede Docker; sem bearer obrigatório) |


Não existe mais transport `stdio` / picker de template no Core.

## 3. Agent BYO

Agent `source=external` → linkar o MCP HTTP nas integrations.

## Limpeza / reset

```bash
make local.reset   # apaga volumes (DB fresca)
make local.up
```

No boot, o BFF faz DROP das colunas stdio legadas se ainda existirem.
Depois registre os MCPs pelo formulário (streamable_http → `http://mcp-*:8787/mcp`).
