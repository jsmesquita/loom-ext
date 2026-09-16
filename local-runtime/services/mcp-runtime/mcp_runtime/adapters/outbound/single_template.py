"""Single-template instance mode (ADR 0014 v2).

One container = one MCP. Env:
  TEMPLATE / MCP_TEMPLATE = allowlisted template id
  MCP_TEMPLATE_PARAMS = JSON object of params
  Secrets: from process env per template secrets[].name

Serves JSON-RPC at POST /mcp (server_id fixed = 1).
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from mcp_runtime.adapters.outbound.yaml_templates import get_template
from mcp_runtime.domain.errors import TemplateError

logger = logging.getLogger("mcp_runtime")

SINGLE_SERVER_ID = 1


def configured_template_id() -> str | None:
    raw = (
        os.environ.get("TEMPLATE", "").strip()
        or os.environ.get("MCP_TEMPLATE", "").strip()
    )
    return raw or None


def template_params_from_env() -> dict[str, str]:
    raw = os.environ.get("MCP_TEMPLATE_PARAMS", "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TemplateError("MCP_TEMPLATE_PARAMS must be JSON object") from exc
    if not isinstance(data, dict):
        raise TemplateError("MCP_TEMPLATE_PARAMS must be a JSON object")
    return {str(k): str(v) for k, v in data.items()}


def secret_refs_for_template(template_id: str) -> list[dict[str, str]]:
    template = get_template(template_id)
    return [
        {"name": item["name"], "backend": "env", "ref": item["name"]}
        for item in (template.get("secrets") or [])
        if isinstance(item, dict) and item.get("name")
    ]


def boot_single_template(supervisor: Any, template_id: str | None = None) -> dict[str, Any]:
    tid = template_id or configured_template_id()
    if not tid:
        raise TemplateError("TEMPLATE / MCP_TEMPLATE is required for single-template mode")
    get_template(tid)  # validate allowlist
    params = template_params_from_env()
    refs = secret_refs_for_template(tid)
    supervisor.register(SINGLE_SERVER_ID, tid, params, refs)
    supervisor.start(SINGLE_SERVER_ID)
    logger.info("single-template ready template=%s endpoint=/mcp", tid)
    return {
        "template_id": tid,
        "server_id": SINGLE_SERVER_ID,
        "endpoint_path": "/mcp",
        "params": params,
    }
