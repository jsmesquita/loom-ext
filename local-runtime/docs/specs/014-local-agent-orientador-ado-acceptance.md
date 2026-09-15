# Spec 014 — Aceite: Orientador local + LiteLLM + Azure DevOps MCP

- **Status:** Em validação (M1 implementado; cenários manuais no compose)
- **Data:** 2026-09-13
- **Atualizado:** 2026-09-15 — `source=external`; MCP `mcp-azure-devops` HTTP
- **Implementa:** [ADR 0005](../adr/0005-local-agent-runtime.md)
- **Depende de:** [011](011-local-agent-runtime-contract.md), [012](012-local-agent-runtime-security.md), [013](013-local-agent-runtime-observability.md), [009 — Azure DevOps MCP](009-azure-devops-mcp-example.md), [004 — cursor planner](004-cursor-custom-llm-provider.md)
- **Não é** um adapter Azure. É o critério de maturidade **M1+M2**.

## 1. Objetivo da prova

Demonstrar que um agente `source=external` (BYO / Orientador) no Chat
usa o catálogo MCP do Loom **de verdade** (HTTP → `mcp-azure-devops`),
com o mesmo gesto de UI dos agentes AgentCore/harness.

```text
Usuario (Chat)
  → Backend (ACL + payload)
    → agent-runtime (tool loop)
      → LiteLLM
           ├─ orientador-academico / mock-* 
           └─ cursor-local → cursor-adapter (planner JSON tool_calls)
      → http://mcp-azure-devops:8787/mcp → Azure DevOps MCP
```

## 2. Pré-condições

1. Stack compose saudável: backend, LiteLLM, `mcp-azure-devops`,
   agent-runtime, cursor-adapter (se usar `cursor-local`), Keycloak, frontend.
2. `AZURE_DEVOPS_PAT` / `AZURE_DEVOPS_ORG` no `.env`; MCP cadastrado no Loom
   como `streamable_http` → `http://mcp-azure-devops:8787/mcp`; tools
   refreshed; `McpServerAccess` para o agente Orientador com
   `selected_tools` (sem tools destrutivas).
3. Usuário `admin` / grupo com `invoke` + acesso ao agente.
4. `AGENT_RUNTIME_URL` / `AGENT_RUNTIME_TOKEN` no backend (overlay).
5. Modelo:
   - **`cursor-local`:** caminho realista de tool loop (planner → MCP).
   - Mock `orientador-academico`: útil para UI/SSE; **não** emite
     `tool_calls` — não prova ADO end-to-end sozinho.

## 3. Cenários de aceite

### 3.1 Connector habilitado funciona

1. Abrir Chat → agente Orientador.
2. Habilitar connector Azure DevOps.
3. Modelo `cursor-local` (recomendado) ou outro com tool calling.
4. Prompt que force tool use (ex. listar projetos / work items da org).
5. **Esperado:** SSE com dados reais do ADO; logs cursor-adapter com
   `planner_tools>0`; agent-runtime faz `tools/list` + `tools/call`;
   PAT ausente do log e do SSE.

### 3.2 ACL deny

1. Remover a tool usada da allowlist (ou negar o server no access).
2. Repetir prompt.
3. **Esperado:** 403 no resolve **ou** `mcp_denied` sem chamada ao
   filho; usuário vê erro claro; processo Azure não é invocado.

### 3.3 Sem connector

1. Desmarcar o connector.
2. Prompt pedindo ADO.
3. **Esperado:** modelo responde sem tools ADO (não inventa sucesso de
   API); payload `mcp_servers` vazio no agent-runtime;
   `planner_tools=0` no adapter.

### 3.4 Isolamento

1. Durante um invoke longo, matar só o worker/sessão do agent-runtime
   (ou cancelar).
2. **Esperado:** backend e UI de catálogo continuam; nova invoke sobe
   sessão nova; `mcp-azure-devops` permanece healthy.

### 3.5 Paridade de transporte

1. Um segundo MCP `streamable_http` (ex. remoto de teste) no catálogo +
   access.
2. Invoke local com esse connector.
3. **Esperado:** mesmo caminho de UI; agent-runtime chama o endpoint
   HTTP; ambos no mesmo payload.

### 3.6 Regressão AgentCore

1. Agente deploy/harness (se houver credencial AWS no ambiente).
2. **Esperado:** comportamento anterior; hosts locais só via URL HTTP
   no catálogo (sem path stdio no Core).

### 3.7 Recreate host MCP

1. `docker compose … restart mcp-azure-devops`.
2. Invoke Orientador + connector (aguardar health).
3. **Esperado:** filho sobe com o container; invoke não depende de
   re-provision no BFF.

## 4. Não-critérios (fora desta prova)

- OBO / Memory / A2A / elicitation
- Container-por-sessão
- Paridade de custo AgentCore
- Trocar o framework interno do agent-runtime
- Passar MCP Loom ao Cursor SDK (proibido — ADR 0005)

## 5. Definição de pronto (M1+M2)

- [x] `source=external` não chama LiteLLM a partir do uvicorn (usa BFF → agent-runtime)
- [x] Contrato 011 (`2026-09-local-1`) + token fail-closed
- [x] Cenário 3.1 verde com `cursor-local` + ADO (validação manual)
- [x] Cenário 3.7 (restart host `TEMPLATE=`)
- [ ] 3.2–3.6 documentados verdes ou N/A
- [x] `make local.up` / overlay menciona agent-runtime + `mcp-*`
- [x] ADR 0005 status **Aceita**
