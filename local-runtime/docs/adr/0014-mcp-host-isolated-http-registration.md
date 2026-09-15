# 14. MCP host isolado — Loom só registra HTTP

- **Status:** Aceito (Loom sem conhecimento de mcp-runtime)
- **Data:** 2026-09-15
- **Decisores:** Mantenedores da plataforma / extensão local
- **Relacionada a:**
  [ADR 0004 — Local MCP Runtime](0004-local-mcp-runtime.md),
  [ADR 0006 — Extensão](0006-local-runtime-extension-repo.md),
  [ADR 0007 — MCP Hub](0007-mcp-hub.md)

## Problema

Acoplar o Core Loom ao lifecycle stdio (`ensure_stdio_ready`, `template_id`,
`MCP_RUNTIME_URL`) misturava control plane com o host de processos. Queremos
o Loom **igual a qualquer MCP remoto**: só catálogo HTTP.

## Decisão

1. **Imagem** `mcp-runtime` (extension) sobe **um MCP por serviço** com
   `TEMPLATE=<id>` → `POST /mcp`.
2. **Compose:** `mcp-azure-devops`, `mcp-rancher`, `mcp-grafana` (mesma imagem).
3. **Loom** cadastra só via formulário nativo:
   `transport=streamable_http` + URL (`http://mcp-azure-devops:8787/mcp`, …)
   + auth `none` / `api_key` / `oauth2`. Sem `stdio`, sem templates no BFF,
   sem `MCP_RUNTIME_URL`.
4. Token local: `MCP_RUNTIME_TOKEN` no backend só para *enrich* de
   `service_bearer` no caminho agent-runtime (mesmo padrão de secret de serviço).
5. **mcp-hub** permanece produto à parte (não alterado neste ADR).

```text
TEMPLATE=…  →  mcp-*:8787/mcp  →  Loom form streamable_http  →  agent-runtime
```

## Consequências

- Novo MCP local: novo serviço no overlay + registro HTTP no Loom.
- Core alinhado ao catálogo upstream (sse / streamable_http).
- Sem client BFF→mcp-runtime; sem path `/s`/`/h`/hosted multi-slug.

## Não-objetivos

- Redesign do mcp-hub
- Split da imagem para outro repositório Git
