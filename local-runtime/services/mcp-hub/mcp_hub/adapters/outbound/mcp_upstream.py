"""Call upstream MCP servers (streamable HTTP JSON-RPC) from the Hub."""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger("mcp_hub.mcp_upstream")

_BLOCKED_HOSTS = frozenset({"metadata.google.internal", "169.254.169.254"})


def _host_allowed(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    host = (parsed.hostname or "").lower()
    if not host or host in _BLOCKED_HOSTS:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    return True


def call_mcp_tool(
    *,
    endpoint_url: str,
    tool_name: str,
    arguments: dict[str, Any],
    timeout: float = 60,
) -> tuple[int, dict[str, Any]]:
    """POST tools/call to ``endpoint_url``. Returns (http_status, envelope)."""
    if not _host_allowed(endpoint_url):
        return 400, {"success": False, "error": "endpoint_blocked"}
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments or {}},
    }
    raw = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        endpoint_url,
        data=raw,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8") or "{}"
            status = resp.status
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8") or "{}"
        status = exc.code
    except Exception as exc:
        logger.warning("mcp_upstream_unreachable: %s", type(exc).__name__)
        return 502, {"success": False, "error": "mcp_unreachable"}

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        # Minimal SSE: last data: line
        data_lines = [ln[5:].strip() for ln in text.splitlines() if ln.startswith("data:")]
        payload = None
        for line in reversed(data_lines):
            try:
                payload = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
        if payload is None:
            return 502, {"success": False, "error": "invalid_mcp_response"}

    if not isinstance(payload, dict):
        return 502, {"success": False, "error": "invalid_mcp_response"}
    if payload.get("error"):
        return status if status >= 400 else 400, {
            "success": False,
            "error": payload.get("error"),
        }
    return 200, {"success": True, "result": payload.get("result") or {}}
