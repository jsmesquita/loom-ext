"""tools/list and tools/call use cases (MCP + agent__*)."""
from __future__ import annotations

import logging
import time
from typing import Any

from mcp_hub.application.ports import HubStore, LoomGateway
from mcp_hub.application.use_cases.session_allowlist import build_session_allowlist
from mcp_hub.domain.naming import expose_tools
from mcp_hub.domain.telemetry import new_request_id, safe_error_reason, telemetry_event

logger = logging.getLogger("mcp_hub")


def mcp_tool_result(text: str, structured: dict[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {
        "content": [{"type": "text", "text": text}],
        "structuredContent": structured,
    }
    if is_error:
        out["isError"] = True
    return out


def list_agent_tools(
    identity: dict[str, Any],
    client: dict[str, Any],
    *,
    loom: LoomGateway,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Return MCP tool defs + map exposed_name → agent_id when agents_enabled."""
    if not bool(client.get("agents_enabled")):
        return [], {}
    code, payload = loom.materialize_agents(
        subject=str(identity["sub"]),
        groups=list(identity.get("groups") or []),
    )
    if code != 200:
        logger.warning("materialize-agents failed status=%s", code)
        return [], {}
    tools: list[dict[str, Any]] = []
    agent_map: dict[str, int] = {}
    for row in payload.get("agents") or []:
        name = str(row.get("exposed_name") or "")
        if not name:
            continue
        tools.append({
            "name": name,
            "description": row.get("description") or row.get("name") or name,
            "inputSchema": row.get("inputSchema") or {"type": "object", "properties": {}},
        })
        try:
            agent_map[name] = int(row["agent_id"])
        except (KeyError, TypeError, ValueError):
            continue
    for mon in payload.get("monitor_tools") or []:
        if isinstance(mon, dict) and mon.get("name"):
            tools.append(mon)
    return tools, agent_map


def handle_agent_tool_call(
    identity: dict[str, Any],
    name: str,
    arguments: dict[str, Any],
    agent_map: dict[str, int],
    *,
    loom: LoomGateway,
    hub_server_ids: list[int] | None = None,
    hub_tool_allowlists: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    subject = str(identity["sub"])
    groups = list(identity.get("groups") or [])
    if name == "agent_run_status":
        sid = str(arguments.get("session_id") or "")
        if not sid:
            return {"jsonrpc": "2.0", "error": {"code": -32602, "message": "session_id_required"}}
        status, result = loom.agents_run(subject=subject, groups=groups, session_id=sid)
        if status == 403:
            return {"error": {"code": -32003, "message": "forbidden"}}
        if status != 200:
            return {"error": {"code": -32004, "message": "run_status_failed"}}
        text = f"status={result.get('status')} session_id={sid}"
        return {"result": mcp_tool_result(text, result)}
    if name == "agent_run_result":
        sid = str(arguments.get("session_id") or "")
        if not sid:
            return {"error": {"code": -32602, "message": "session_id_required"}}
        status, result = loom.agents_run(subject=subject, groups=groups, session_id=sid)
        if status == 403:
            return {"error": {"code": -32003, "message": "forbidden"}}
        if status != 200:
            return {"error": {"code": -32004, "message": "run_result_failed"}}
        if result.get("status") != "complete":
            return {
                "result": mcp_tool_result(
                    f"Run not complete yet (status={result.get('status')})",
                    result,
                    is_error=True,
                )
            }
        return {"result": mcp_tool_result(str(result.get("text") or ""), result)}
    if name.startswith("agent__"):
        agent_id = agent_map.get(name)
        if agent_id is None:
            code, payload = loom.materialize_agents(subject=subject, groups=groups)
            if code == 200:
                for row in payload.get("agents") or []:
                    if row.get("exposed_name") == name:
                        try:
                            agent_id = int(row["agent_id"])
                        except (TypeError, ValueError):
                            agent_id = None
                        break
        if agent_id is None:
            return {"error": {"code": -32003, "message": "tool_not_allowed"}}
        prompt = str(arguments.get("prompt") or "")
        if not prompt:
            return {"error": {"code": -32602, "message": "prompt_required"}}
        wait = str(arguments.get("wait") or "accepted")
        mode = "sync" if wait == "complete" else "async"
        sid = arguments.get("session_id")
        status, result = loom.agents_invoke(
            subject=subject,
            groups=groups,
            agent_id=agent_id,
            prompt=prompt,
            session_id=str(sid) if sid else None,
            mode=mode,
            hub_server_ids=hub_server_ids,
            hub_tool_allowlists=hub_tool_allowlists,
            mcp_client_slug=str(identity.get("mcp_client_slug") or "") or None,
            hub_session_id=str(identity.get("connection_id") or "") or None,
            wait_mode=wait,
        )
        if status == 403:
            return {"error": {"code": -32003, "message": "agent_forbidden"}}
        if status >= 400:
            detail = result.get("detail") or result.get("error") or "invoke_failed"
            return {"error": {"code": -32004, "message": str(detail)}}
        st = str(result.get("status") or "")
        text = (
            f"Run accepted. session_id={result.get('session_id')}"
            if st == "accepted"
            else (result.get("text") or f"status={st} session_id={result.get('session_id')}")
        )
        return {"result": mcp_tool_result(str(text), result, is_error=st in ("error",))}
    return {"error": {"code": -32003, "message": "tool_not_allowed"}}


def list_tools(
    identity: dict[str, Any],
    *,
    store: HubStore,
    loom: LoomGateway,
) -> list[dict[str, Any]]:
    t0 = time.perf_counter()
    request_id = new_request_id()
    slug, allow, _mapping, client = build_session_allowlist(identity, store=store, loom=loom)
    tools, _ = expose_tools(allow.get("entries") or [])
    if client and str(client.get("status") or "") == "enabled":
        agent_tools, _amap = list_agent_tools(identity, client, loom=loom)
        tools = list(tools) + list(agent_tools)
        tools.sort(key=lambda t: t.get("name") or "")
    duration_ms = int((time.perf_counter() - t0) * 1000)
    if slug and slug != "unbound":
        store.touch_last_seen(slug)
    store.record_telemetry(
        telemetry_event(
            event_type="tools_list",
            request_id=request_id,
            hub_session_id=str(identity.get("connection_id") or ""),
            mcp_client_slug=slug if slug != "unbound" else None,
            subject=str(identity.get("sub") or ""),
            groups=list(identity.get("groups") or []),
            phase="ok",
            duration_ms=duration_ms,
            meta={
                "tool_count": len(tools),
                "server_count": len(allow.get("entries") or []),
                "agents_enabled": bool(client and client.get("agents_enabled")),
            },
        )
    )
    return tools


def call_tool(
    identity: dict[str, Any],
    *,
    name: str,
    arguments: dict[str, Any],
    store: HubStore,
    loom: LoomGateway,
) -> dict[str, Any]:
    """Return JSON-RPC ``result`` or ``error`` object (without jsonrpc/id wrapper)."""
    t0 = time.perf_counter()
    request_id = new_request_id()
    groups = list(identity.get("groups") or [])
    slug, allow, mapping, client = build_session_allowlist(identity, store=store, loom=loom)
    if slug and slug != "unbound":
        store.touch_last_seen(slug)
    if not isinstance(arguments, dict):
        arguments = {}
    hub_session_id = str(identity.get("connection_id") or "")
    subject = str(identity.get("sub") or "")

    def _emit(*, phase: str, error_code: str | None = None, meta: dict[str, Any] | None = None, server_id: int | None = None, original: str | None = None) -> None:
        store.record_telemetry(
            telemetry_event(
                event_type="tools_call",
                request_id=request_id,
                hub_session_id=hub_session_id,
                mcp_client_slug=slug if slug != "unbound" else None,
                subject=subject,
                groups=groups,
                tool_name=name,
                original_tool=original,
                server_id=server_id,
                phase=phase,
                error_code=error_code,
                duration_ms=int((time.perf_counter() - t0) * 1000),
                meta=meta,
            )
        )

    agents_on = bool(client and client.get("agents_enabled") and client.get("status") == "enabled")
    if name.startswith("agent__") or name in ("agent_run_status", "agent_run_result"):
        if not agents_on:
            _emit(phase="denied", error_code="agents_disabled")
            return {"error": {"code": -32003, "message": "agents_disabled"}}
        _agent_tools, agent_map = list_agent_tools(identity, client or {}, loom=loom)
        hub_server_ids: list[int] = []
        hub_tool_allowlists: dict[str, list[str]] = {}
        for entry in allow.get("entries") or []:
            try:
                sid = int(entry["server_id"])
            except (KeyError, TypeError, ValueError):
                continue
            hub_server_ids.append(sid)
            names = [
                str(t.get("name"))
                for t in (entry.get("tools") or [])
                if isinstance(t, dict) and t.get("name")
            ]
            hub_tool_allowlists[str(sid)] = names
        identity = {**identity, "mcp_client_slug": slug if slug != "unbound" else None}
        handled = handle_agent_tool_call(
            identity,
            name,
            arguments,
            agent_map,
            loom=loom,
            hub_server_ids=hub_server_ids,
            hub_tool_allowlists=hub_tool_allowlists,
        )
        if "error" in handled and "result" not in handled:
            err = handled.get("error") or {}
            reason = safe_error_reason(err)
            _emit(
                phase="denied" if err.get("code") == -32003 else "error",
                error_code=str(err.get("message") or "error"),
                meta={
                    "wait": arguments.get("wait"),
                    "agent_id": agent_map.get(name),
                    **({"reason": reason} if reason else {}),
                },
            )
            return {"error": handled["error"]}
        result = handled.get("result") or {}
        structured = result.get("structuredContent") if isinstance(result, dict) else None
        meta: dict[str, Any] = {"wait": arguments.get("wait")}
        if isinstance(structured, dict):
            if structured.get("session_id"):
                meta["loom_session_id"] = structured.get("session_id")
            if structured.get("invocation_id"):
                meta["loom_invocation_id"] = structured.get("invocation_id")
            if structured.get("agent_id") is not None:
                meta["agent_id"] = structured.get("agent_id")
            if structured.get("status"):
                meta["run_status"] = structured.get("status")
        _emit(phase="ok", meta=meta, original=None)
        return {"result": result}
    if name not in mapping:
        _emit(phase="denied", error_code="tool_not_allowed")
        return {"error": {"code": -32003, "message": "tool_not_allowed"}}
    server_id, original = mapping[name]
    status, result = loom.tools_call(
        subject=subject,
        groups=groups,
        tool_name=name,
        arguments=arguments,
        server_id=server_id,
        original_tool_name=original,
    )
    if status == 403:
        _emit(phase="denied", error_code="tool_not_allowed", server_id=server_id, original=original)
        return {"error": {"code": -32003, "message": "tool_not_allowed"}}
    if status != 200 or not result.get("success"):
        reason = safe_error_reason(
            result.get("error")
            or result.get("message")
            or result.get("detail")
            or f"http_{status}"
        )
        _emit(
            phase="error",
            error_code="tool_call_failed",
            server_id=server_id,
            original=original,
            meta={"reason": reason, "http_status": status} if reason else {"http_status": status},
        )
        return {"error": {"code": -32004, "message": "tool_call_failed"}}
    _emit(phase="ok", server_id=server_id, original=original)
    return {"result": result.get("result") or {}}
