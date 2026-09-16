# Local MCP runtime

One container = one MCP (`TEMPLATE=<id>` → `POST /mcp`).

Loom registers these as normal `streamable_http` servers (native form). The
BFF does not call mcp-runtime APIs.

```text
Loom catalog (streamable_http)
  → http://mcp-azure-devops:8787/mcp
    → TEMPLATE=azure-devops child (stdio inside the container)
```

Templates: `templates/*.yaml`. Params: `MCP_TEMPLATE_PARAMS` (JSON). Secrets: env.
`TEMPLATE` is required at boot.

```text
make local.mcp-runtime.test
```

## Package layout

```text
mcp-runtime/
  templates/
  mcp_runtime/
    domain/
    application/
    adapters/
    echo_child.py
    __main__.py
```
