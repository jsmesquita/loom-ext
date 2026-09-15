"""Native Loom agents APIs for Hub agent__* tools (ADR 0015)."""
from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
from typing import Any

from mcp_hub.adapters.outbound.loom_user_http import loom_get, loom_post

logger = logging.getLogger("mcp_hub.agents_native")
_SLUG_RE = re.compile(r"[^a-z0-9]+")

AGENT_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["prompt"],
    "properties": {
        "prompt": {"type": "string"},
        "session_id": {"type": "string"},
        "wait": {
            "type": "string",
            "enum": ["accepted", "complete"],
            "default": "accepted",
        },
    },
}

STATUS_TOOL: dict[str, Any] = {
    "name": "agent_run_status",
    "description": "Poll status of a Loom agent run started via agent__* tools.",
    "inputSchema": {
        "type": "object",
        "required": ["session_id"],
        "properties": {"session_id": {"type": "string"}},
    },
}

RESULT_TOOL: dict[str, Any] = {
    "name": "agent_run_result",
    "description": "Fetch final text of a completed Loom agent run.",
    "inputSchema": {
        "type": "object",
        "required": ["session_id"],
        "properties": {"session_id": {"type": "string"}},
    },
}

_runs_lock = threading.Lock()
_runs: dict[str, dict[str, Any]] = {}


def _agent_slug(name: str, agent_id: int) -> str:
    raw = (name or f"agent-{agent_id}").lower()
    slug = _SLUG_RE.sub("-", raw).strip("-")
    return slug or f"agent-{agent_id}"


def _parse_sse(raw: str) -> tuple[str, str, str | None, str | None]:
    """Return (text, status, session_id, error)."""
    texts: list[str] = []
    status = "running"
    session_id: str | None = None
    err: str | None = None
    for block in raw.split("\n\n"):
        if not block.strip():
            continue
        event = "message"
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
        if not data_lines:
            continue
        try:
            payload = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if event == "session_start" and payload.get("session_id"):
            session_id = str(payload["session_id"])
        if event == "chunk" and payload.get("text"):
            texts.append(str(payload["text"]))
        if event == "session_end":
            status = "complete"
            if payload.get("session_id"):
                session_id = str(payload["session_id"])
        if event == "error":
            status = "error"
            err = str(payload.get("message") or "invoke_error")
    return "".join(texts), status, session_id, err


def materialize_agents(*, access_token: str) -> tuple[int, dict[str, Any]]:
    code, payload = loom_get("/api/agents", access_token=access_token)
    if code != 200 or not isinstance(payload, list):
        return code if code >= 400 else 502, {"agents": [], "monitor_tools": []}
    slug_counts: dict[str, int] = {}
    rows: list[dict[str, Any]] = []
    for a in payload:
        if not isinstance(a, dict):
            continue
        try:
            agent_id = int(a["id"])
        except (KeyError, TypeError, ValueError):
            continue
        name = str(a.get("name") or f"agent-{agent_id}")
        slug = _agent_slug(name, agent_id)
        slug_counts[slug] = slug_counts.get(slug, 0) + 1
        rows.append({"agent_id": agent_id, "name": name, "slug": slug, "description": a.get("description")})
    agents: list[dict[str, Any]] = []
    for row in rows:
        collide = slug_counts[row["slug"]] > 1
        exposed = f"agent__{row['slug']}__{row['agent_id']}" if collide else f"agent__{row['slug']}"
        agents.append({
            "agent_id": row["agent_id"],
            "slug": row["slug"],
            "exposed_name": exposed,
            "name": row["name"],
            "description": (row.get("description") or row["name"] or exposed)[:500],
            "inputSchema": AGENT_INPUT_SCHEMA,
            "source": "external",
        })
    agents.sort(key=lambda x: x["exposed_name"])
    return 200, {"agents": agents, "monitor_tools": [STATUS_TOOL, RESULT_TOOL]}


def _set_run(session_id: str, **fields: Any) -> None:
    with _runs_lock:
        cur = dict(_runs.get(session_id) or {})
        cur.update(fields)
        cur["session_id"] = session_id
        _runs[session_id] = cur


def _get_run(session_id: str) -> dict[str, Any] | None:
    with _runs_lock:
        row = _runs.get(session_id)
        return dict(row) if row else None


def _consume_invoke(
    *,
    access_token: str,
    agent_id: int,
    prompt: str,
    session_id: str | None,
    connector_ids: list[int] | None,
    run_key: str,
    timeout_s: int,
) -> None:
    body: dict[str, Any] = {
        "prompt": prompt,
        "qualifier": "DEFAULT",
    }
    if session_id:
        body["session_id"] = session_id
    if connector_ids:
        body["connector_ids"] = connector_ids
    status, raw = loom_post(
        f"/api/agents/{agent_id}/invoke",
        body,
        access_token=access_token,
        timeout=float(timeout_s + 30),
        accept="text/event-stream",
    )
    if status >= 400:
        detail = raw if isinstance(raw, str) else (raw.get("detail") if isinstance(raw, dict) else "invoke_failed")
        _set_run(run_key, status="error", error_message=str(detail), text=None)
        return
    text_raw = raw if isinstance(raw, str) else ""
    text, st, sid, err = _parse_sse(text_raw)
    final_sid = sid or run_key
    if final_sid != run_key:
        with _runs_lock:
            data = _runs.pop(run_key, {})
            data.update({
                "session_id": final_sid,
                "status": "error" if err else st,
                "text": text or None,
                "error_message": err,
                "agent_id": agent_id,
            })
            _runs[final_sid] = data
            # Keep provisional key as alias so early pollers still resolve.
            _runs[run_key] = {**data, "session_id": final_sid}
    else:
        _set_run(
            run_key,
            status="error" if err else st,
            text=text or None,
            error_message=err,
            agent_id=agent_id,
        )


def agents_invoke(
    *,
    access_token: str,
    agent_id: int,
    prompt: str,
    session_id: str | None = None,
    mode: str = "async",
    timeout_s: int = 120,
    hub_server_ids: list[int] | None = None,
) -> tuple[int, dict[str, Any]]:
    run_key = session_id or str(uuid.uuid4())
    _set_run(run_key, status="running", agent_id=agent_id, text=None)
    if mode == "sync":
        _consume_invoke(
            access_token=access_token,
            agent_id=agent_id,
            prompt=prompt,
            session_id=session_id,
            connector_ids=hub_server_ids,
            run_key=run_key,
            timeout_s=timeout_s,
        )
        row = _get_run(run_key) or {}
        # after sync, session id may have changed
        if row.get("session_id") and row["session_id"] != run_key:
            row = _get_run(str(row["session_id"])) or row
        return 200, {
            "status": row.get("status") or "error",
            "session_id": row.get("session_id") or run_key,
            "agent_id": agent_id,
            "text": row.get("text"),
            "error_message": row.get("error_message"),
        }

    thread = threading.Thread(
        target=_consume_invoke,
        kwargs={
            "access_token": access_token,
            "agent_id": agent_id,
            "prompt": prompt,
            "session_id": session_id,
            "connector_ids": hub_server_ids,
            "run_key": run_key,
            "timeout_s": timeout_s,
        },
        daemon=True,
    )
    thread.start()
    # brief wait for session_start
    deadline = time.time() + 2.0
    sid = run_key
    while time.time() < deadline:
        row = _get_run(run_key)
        if row and row.get("session_id") and row["session_id"] != run_key:
            sid = str(row["session_id"])
            break
        # also check if run_key itself updated in place with session from SSE before migrate
        time.sleep(0.05)
    return 200, {"status": "accepted", "session_id": sid, "agent_id": agent_id}


def agents_run(*, session_id: str) -> tuple[int, dict[str, Any]]:
    row = _get_run(session_id)
    if row is None:
        return 404, {"error": "not_found", "denied": False}
    return 200, {
        "session_id": session_id,
        "agent_id": row.get("agent_id"),
        "status": row.get("status") or "running",
        "preview": (str(row["text"])[:400] if row.get("text") else None),
        "text": row.get("text") if row.get("status") == "complete" else None,
        "error_message": row.get("error_message"),
    }
