# Spec 009 — Azure DevOps MCP (exemplo)

- **Status:** Aceita (alinhada a ADR 0014)
- **Data:** 2026-09-12
- **Atualizado:** 2026-09-15 — registro HTTP; serviço `mcp-azure-devops`
- **Implementa:** [ADR 0014](../adr/0014-mcp-host-isolated-http-registration.md)
- **Não é** um adapter no Core. É template YAML + secret no overlay.

## 1. Fluxo

```text
Loom (catálogo streamable_http + ACL)
  → http://mcp-azure-devops:8787/mcp  (Bearer MCP_RUNTIME_TOKEN)
    → TEMPLATE=azure-devops → npx @azure-devops/mcp <org>
      → Azure DevOps REST
```

## 2. Overlay / env

| Item | Valor |
|------|--------|
| Serviço | `mcp-azure-devops` |
| `TEMPLATE` | `azure-devops` |
| `AZURE_DEVOPS_ORG` | org no `MCP_TEMPLATE_PARAMS` |
| `AZURE_DEVOPS_PAT` | secret do template |

## 3. Registro no Loom

Formulário MCP nativo:

- transport: `streamable_http`
- endpoint: `http://mcp-azure-devops:8787/mcp`
- auth: `none` (enrich local injeta bearer de serviço)

## 4. Fora de escopo

- `transport=stdio` no Core
- Adapter Azure no BFF
