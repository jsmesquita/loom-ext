"""Build Hub allowlist entries from Loom catalog APIs ∩ profile grants (ADR 0015)."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from mcp_hub.adapters.outbound.loom_user_http import loom_get

logger = logging.getLogger("mcp_hub.catalog")
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(name: str, server_id: int) -> str:
    raw = (name or f"server-{server_id}").lower()
    slug = _SLUG_RE.sub("-", raw).strip("-")
    return slug or f"server-{server_id}"


def _iso_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def materialize_entries_from_grants(
    *,
    access_token: str,
    subject: str,
    connection_id: str,
    mcp_client_slug: str,
    client_status: str,
    grants: list[dict[str, Any]],
) -> tuple[int, dict[str, Any]]:
    """Fetch server+tools from Loom for each grant server_id and filter tools."""
    if client_status != "enabled":
        return 200, {
            "subject": subject,
            "hub_session_id": connection_id,
            "mcp_client_slug": mcp_client_slug,
            "client_status": client_status,
            "entries": [],
            "generated_at": _iso_z(),
        }

    per_server: dict[int, set[str] | None] = {}
    for grant in grants:
        try:
            server_id = int(grant["server_id"])
        except (KeyError, TypeError, ValueError):
            continue
        level = str(grant.get("access_level") or "selected_tools")
        if level == "all_tools":
            per_server[server_id] = None
            continue
        names = grant.get("tool_names") or []
        if not isinstance(names, list):
            continue
        name_set = {str(n) for n in names if n}
        current = per_server.get(server_id, "__missing__")
        if current == "__missing__":
            per_server[server_id] = name_set
        elif current is None:
            continue
        else:
            current.update(name_set)

    entries: list[dict[str, Any]] = []
    for server_id, allowed in per_server.items():
        code, server = loom_get(f"/api/mcp/servers/{server_id}", access_token=access_token)
        if code != 200 or not isinstance(server, dict):
            logger.info("catalog_server_skip id=%s status=%s", server_id, code)
            continue
        if str(server.get("status") or "") == "inactive":
            continue
        tcode, tools_payload = loom_get(
            f"/api/mcp/servers/{server_id}/tools",
            access_token=access_token,
        )
        tools_rows = tools_payload if isinstance(tools_payload, list) else []
        if tcode != 200:
            tools_rows = []
        tools: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in tools_rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("tool_name") or row.get("name") or "")
            if not name:
                continue
            if allowed is not None and name not in allowed:
                continue
            seen.add(name)
            tools.append({
                "name": name,
                "description": row.get("description") or "",
                "inputSchema": row.get("input_schema") or row.get("inputSchema")
                or {"type": "object", "properties": {}},
            })
        if allowed is not None:
            for name in sorted(allowed):
                if name in seen:
                    continue
                tools.append({
                    "name": name,
                    "description": "",
                    "inputSchema": {"type": "object", "properties": {}},
                })
        if not tools:
            continue
        entries.append({
            "server_id": server_id,
            "server_slug": _slug(str(server.get("name") or ""), server_id),
            "endpoint_url": str(server.get("endpoint_url") or ""),
            "transport": str(server.get("transport_type") or "streamable_http"),
            "tools": tools,
        })

    return 200, {
        "subject": subject,
        "hub_session_id": connection_id,
        "mcp_client_slug": mcp_client_slug,
        "client_status": client_status,
        "entries": entries,
        "generated_at": _iso_z(),
    }
