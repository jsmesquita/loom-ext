"""MCP Hub control-plane helpers (ADR 0007, specs 016-019). OAuth era — no mint."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.dependencies.auth import UserInfo
from app.models.agent import Agent
from app.models.mcp import McpServer, McpServerAccess, McpTool
from app.services.mcp import invoke_mcp_tool
from app.services.mcp_access import allowed_tool_names, get_access_rule

CONTRACT_VERSION = "2026-09-hub-1"
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def hub_public_url() -> str:
    return os.getenv("MCP_HUB_PUBLIC_URL", "http://127.0.0.1:8790/mcp").rstrip("/")


def hub_service_token() -> str:
    return os.environ.get("MCP_HUB_SERVICE_TOKEN", "").strip()


def user_can_invoke_agent(user: UserInfo, agent: Agent) -> bool:
    if "g-admins-super" in (user.groups or []):
        return True
    tags = agent.get_tags() if hasattr(agent, "get_tags") else {}
    agent_group = (tags or {}).get("loom:group", "") or ""
    if not agent_group:
        return True
    if "t-admin" in (user.groups or []):
        admin_groups = [g for g in user.groups if g.startswith("g-admins-")]
        allowed = [g.replace("g-admins-", "", 1) for g in admin_groups]
    else:
        user_groups = [g for g in user.groups if g.startswith("g-users-")]
        allowed = [g.replace("g-users-", "", 1) for g in user_groups]
    return agent_group in allowed


def server_slug(server: McpServer) -> str:
    raw = (server.name or f"server-{server.id}").lower()
    slug = _SLUG_RE.sub("-", raw).strip("-")
    return slug or f"server-{server.id}"


def _entries_from_server_tools(
    db: Session,
    per_server: dict[int, set[str] | None],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for server_id, allowed in per_server.items():
        server = db.query(McpServer).filter(McpServer.id == server_id).first()
        if server is None or server.status == "inactive":
            continue
        tools_rows = db.query(McpTool).filter(McpTool.server_id == server_id).all()
        tools: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in tools_rows:
            if allowed is not None and row.tool_name not in allowed:
                continue
            seen.add(row.tool_name)
            tools.append({
                "name": row.tool_name,
                "description": row.description or "",
                "inputSchema": row.get_input_schema() or {"type": "object", "properties": {}},
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
        transport = server.transport_type
        entries.append({
            "server_id": server.id,
            "server_slug": server_slug(server),
            "endpoint_url": server.endpoint_url,
            "transport": transport,
            "tools": tools,
        })
    return entries


def build_allowlist(db: Session, user: UserInfo) -> dict[str, Any]:
    """Interim union-by-agents allowlist (ADR 0007). Prefer materialize_from_grants."""
    agents = db.query(Agent).all()
    invocavel = [a for a in agents if user_can_invoke_agent(user, a)]
    per_server: dict[int, set[str] | None] = {}
    for agent in invocavel:
        rules = db.query(McpServerAccess).filter(McpServerAccess.persona_id == agent.id).all()
        for rule in rules:
            names = allowed_tool_names(rule)
            if names is None:
                per_server[rule.server_id] = None
                continue
            current = per_server.get(rule.server_id, "__missing__")
            if current == "__missing__":
                per_server[rule.server_id] = set(names)
            elif current is None:
                continue
            else:
                current.update(names)

    return {
        "subject": user.sub,
        "entries": _entries_from_server_tools(db, per_server),
        "generated_at": _iso_z(datetime.utcnow()),
    }


def materialize_from_grants(
    db: Session,
    user: UserInfo,
    *,
    hub_session_id: str,
    mcp_client_slug: str,
    client_status: str,
    allowed_groups: list[str],
    grants: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build allowlist entries from extension MCP Client grants (ADR 0008)."""
    if client_status != "enabled":
        return {
            "subject": user.sub,
            "hub_session_id": hub_session_id,
            "mcp_client_slug": mcp_client_slug,
            "client_status": client_status,
            "entries": [],
            "generated_at": _iso_z(datetime.utcnow()),
        }
    if allowed_groups:
        user_groups = set(user.groups or [])
        if "g-admins-super" not in user_groups and not (user_groups & set(allowed_groups)):
            return {
                "subject": user.sub,
                "hub_session_id": hub_session_id,
                "mcp_client_slug": mcp_client_slug,
                "client_status": client_status,
                "entries": [],
                "generated_at": _iso_z(datetime.utcnow()),
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

    return {
        "subject": user.sub,
        "hub_session_id": hub_session_id,
        "mcp_client_slug": mcp_client_slug,
        "client_status": client_status,
        "entries": _entries_from_server_tools(db, per_server),
        "generated_at": _iso_z(datetime.utcnow()),
    }


def expose_tools(entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, tuple[int, str]]]:
    name_owners: dict[str, list[tuple[int, str, dict[str, Any], str]]] = {}
    for entry in entries:
        sid = int(entry["server_id"])
        slug = str(entry["server_slug"])
        for tool in entry.get("tools") or []:
            original = str(tool["name"])
            name_owners.setdefault(original, []).append((sid, slug, tool, original))

    exposed: list[dict[str, Any]] = []
    mapping: dict[str, tuple[int, str]] = {}
    for _original, owners in name_owners.items():
        collide = len({sid for sid, _, _, _ in owners}) > 1
        for sid, slug, tool, orig in owners:
            exposed_name = f"{slug}__{orig}" if collide else orig
            mapping[exposed_name] = (sid, orig)
            exposed.append({
                "name": exposed_name,
                "description": tool.get("description") or "",
                "inputSchema": tool.get("inputSchema") or {"type": "object", "properties": {}},
            })
    exposed.sort(key=lambda t: t["name"])
    return exposed, mapping


def call_hub_tool(
    db: Session,
    user: UserInfo,
    exposed_name: str,
    arguments: dict[str, Any],
    *,
    server_id: int | None = None,
    original_tool_name: str | None = None,
) -> dict[str, Any]:
    """Execute a Hub tool. Prefer explicit server_id+original from Hub grant mapping."""
    if server_id is not None and original_tool_name:
        resolved_server_id = server_id
        original = original_tool_name
    else:
        # Interim fallback: union allowlist (pre-ADR 0008 path)
        allowlist = build_allowlist(db, user)
        _exposed, mapping = expose_tools(allowlist["entries"])
        if exposed_name not in mapping:
            return {"success": False, "error": "tool_not_allowed", "denied": True}
        resolved_server_id, original = mapping[exposed_name]
        if not _subject_still_allows(db, user, resolved_server_id, original):
            return {"success": False, "error": "tool_not_allowed", "denied": True}

    server = db.query(McpServer).filter(McpServer.id == resolved_server_id).first()
    if server is None:
        return {"success": False, "error": "server_not_found", "denied": True}
    return invoke_mcp_tool(server, original, arguments or {})


def _subject_still_allows(db: Session, user: UserInfo, server_id: int, tool_name: str) -> bool:
    for agent in db.query(Agent).all():
        if not user_can_invoke_agent(user, agent):
            continue
        rule = get_access_rule(db, server_id, agent.id)
        if rule is None:
            continue
        names = allowed_tool_names(rule)
        if names is None or tool_name in names:
            return True
    return False


def _iso_z(value: datetime) -> str:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
