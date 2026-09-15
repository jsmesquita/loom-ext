"""Persistent MCP Client registry for the Hub (ADR 0008 / specs 021-022) — JSON file."""
from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from mcp_hub.domain.client_records import client_summary, normalize_grant, refresh_allowed_groups

_lock = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def store_path() -> str:
    return os.environ.get("MCP_HUB_STORE_PATH", "/data/hub_clients.json")


def _empty() -> dict[str, Any]:
    return {"clients": {}, "session_bindings": {}, "telemetry": [], "version": 1}


def _load() -> dict[str, Any]:
    path = store_path()
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return _empty()
        data.setdefault("clients", {})
        data.setdefault("session_bindings", {})
        data.setdefault("telemetry", [])
        return data
    except FileNotFoundError:
        return _empty()
    except json.JSONDecodeError:
        return _empty()


def _save(data: dict[str, Any]) -> None:
    path = store_path()
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
    os.replace(tmp, path)


def list_clients(status: str | None = None) -> list[dict[str, Any]]:
    with _lock:
        data = _load()
        rows = list(data["clients"].values())
    if status:
        rows = [c for c in rows if c.get("status") == status]
    rows.sort(key=lambda c: c.get("last_seen_at") or c.get("first_seen_at") or "")
    return [client_summary(c) for c in rows]


def get_client(slug: str, *, include_grants: bool = False) -> dict[str, Any] | None:
    with _lock:
        row = _load()["clients"].get(slug)
        if row is None:
            return None
        if include_grants:
            return deepcopy(row)
        return client_summary(row)


def get_profile_grants(slug: str, group: str) -> dict[str, Any] | None:
    group = str(group or "").strip()
    if not group:
        return None
    with _lock:
        row = _load()["clients"].get(slug)
        if row is None:
            return None
        grants = [
            deepcopy(g)
            for g in (row.get("grants") or [])
            if str(g.get("group") or "") == group
        ]
    return {"slug": slug, "group": group, "grants": grants}


def put_profile_grants(slug: str, group: str, grants: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Replace grants for one IdP profile only; leave other profiles untouched."""
    group = str(group or "").strip()
    if not group:
        return None
    with _lock:
        data = _load()
        row = data["clients"].get(slug)
        if row is None:
            return None
        kept = [
            g for g in (row.get("grants") or [])
            if str(g.get("group") or "") != group
        ]
        cleaned: list[dict[str, Any]] = []
        for g in grants:
            item = normalize_grant(g, group=group)
            if item is not None:
                cleaned.append(item)
        row["grants"] = kept + cleaned
        refresh_allowed_groups(row)
        _save(data)
        return {"slug": slug, "group": group, "grants": deepcopy(cleaned)}


def put_grants(slug: str, grants: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Replace all grants (admin/full sync). Prefer ``put_profile_grants`` for UI."""
    with _lock:
        data = _load()
        row = data["clients"].get(slug)
        if row is None:
            return None
        cleaned: list[dict[str, Any]] = []
        for g in grants:
            group = str(g.get("group") or "").strip()
            if not group:
                continue
            item = normalize_grant(g, group=group)
            if item is not None:
                cleaned.append(item)
        row["grants"] = cleaned
        refresh_allowed_groups(row)
        _save(data)
        return deepcopy(row)


def upsert_from_initialize(
    *,
    hub_session_id: str,
    slug: str,
    declared_name: str,
    declared_version: str,
    declared_family: str,
    display_name: str | None = None,
) -> dict[str, Any]:
    with _lock:
        data = _load()
        now = _now()
        existing = data["clients"].get(slug)
        if existing is None:
            row = {
                "slug": slug,
                "display_name": display_name or declared_name or slug,
                "declared_name": declared_name,
                "declared_version": declared_version,
                "declared_family": declared_family,
                "status": "discovered",
                "agents_enabled": False,
                "allowed_groups": [],
                "grants": [],
                "first_seen_at": now,
                "last_seen_at": now,
            }
            data["clients"][slug] = row
        else:
            existing["declared_name"] = declared_name
            existing["declared_version"] = declared_version
            existing["declared_family"] = declared_family
            existing["last_seen_at"] = now
            if not existing.get("display_name"):
                existing["display_name"] = display_name or declared_name or slug
            row = existing
        data["session_bindings"][hub_session_id] = {
            "mcp_client_slug": slug,
            "bound_at": now,
        }
        _save(data)
        return deepcopy(row)


def bind_session(hub_session_id: str, slug: str) -> None:
    with _lock:
        data = _load()
        data["session_bindings"][hub_session_id] = {
            "mcp_client_slug": slug,
            "bound_at": _now(),
        }
        _save(data)


def session_client_slug(hub_session_id: str) -> str | None:
    with _lock:
        bind = _load()["session_bindings"].get(hub_session_id) or {}
        slug = bind.get("mcp_client_slug")
        return str(slug) if slug else None


def patch_client(slug: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    with _lock:
        data = _load()
        row = data["clients"].get(slug)
        if row is None:
            return None
        if "status" in patch and patch["status"] in ("discovered", "enabled", "disabled"):
            row["status"] = patch["status"]
        if "display_name" in patch and isinstance(patch["display_name"], str):
            row["display_name"] = patch["display_name"][:128]
        if "allowed_groups" in patch and isinstance(patch["allowed_groups"], list):
            row["allowed_groups"] = [str(g) for g in patch["allowed_groups"][:64]]
        if "agents_enabled" in patch:
            row["agents_enabled"] = bool(patch["agents_enabled"])
        _save(data)
        return deepcopy(row)


def delete_client(slug: str) -> bool:
    with _lock:
        data = _load()
        if slug not in data["clients"]:
            return False
        del data["clients"][slug]
        data["session_bindings"] = {
            sid: b
            for sid, b in data["session_bindings"].items()
            if b.get("mcp_client_slug") != slug
        }
        _save(data)
        return True


def load_snapshot() -> dict[str, Any]:
    """Return raw JSON snapshot (for one-shot migration to Postgres)."""
    with _lock:
        return deepcopy(_load())


class FileHubStore:
    """Outbound adapter implementing ``HubStore`` (JSON file fallback)."""

    def store_path(self) -> str:
        return store_path()

    def list_clients(self, status: str | None = None) -> list[dict[str, Any]]:
        return list_clients(status)

    def get_client(self, slug: str, *, include_grants: bool = False) -> dict[str, Any] | None:
        return get_client(slug, include_grants=include_grants)

    def get_profile_grants(self, slug: str, group: str) -> dict[str, Any] | None:
        return get_profile_grants(slug, group)

    def put_profile_grants(
        self, slug: str, group: str, grants: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        return put_profile_grants(slug, group, grants)

    def put_grants(self, slug: str, grants: list[dict[str, Any]]) -> dict[str, Any] | None:
        return put_grants(slug, grants)

    def upsert_from_initialize(
        self,
        *,
        hub_session_id: str,
        slug: str,
        declared_name: str,
        declared_version: str,
        declared_family: str,
        display_name: str | None = None,
    ) -> dict[str, Any]:
        return upsert_from_initialize(
            hub_session_id=hub_session_id,
            slug=slug,
            declared_name=declared_name,
            declared_version=declared_version,
            declared_family=declared_family,
            display_name=display_name,
        )

    def session_client_slug(self, hub_session_id: str) -> str | None:
        return session_client_slug(hub_session_id)

    def patch_client(self, slug: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        return patch_client(slug, patch)

    def delete_client(self, slug: str) -> bool:
        return delete_client(slug)

    def touch_last_seen(self, slug: str) -> None:
        if not slug:
            return
        with _lock:
            data = _load()
            row = data["clients"].get(slug)
            if row is None:
                return
            row["last_seen_at"] = _now()
            _save(data)

    def record_telemetry(self, event: dict[str, Any]) -> None:
        with _lock:
            data = _load()
            events = data.setdefault("telemetry", [])
            if not isinstance(events, list):
                events = []
                data["telemetry"] = events
            entry = dict(event)
            entry["occurred_at"] = _now()
            events.append(entry)
            # Cap file growth
            if len(events) > 5000:
                data["telemetry"] = events[-4000:]
            _save(data)

    def analytics_summary(self, *, hours: int = 24, slug: str | None = None) -> dict[str, Any]:
        from datetime import timedelta

        hours = max(1, min(int(hours or 24), 24 * 90))
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        with _lock:
            data = _load()
            events = list(data.get("telemetry") or [])
            clients_map = data.get("clients") or {}
        by_slug: dict[str, dict[str, Any]] = {}
        for ev in events:
            if not isinstance(ev, dict):
                continue
            ts = str(ev.get("occurred_at") or "")
            try:
                occurred = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                continue
            if occurred < cutoff:
                continue
            s = str(ev.get("mcp_client_slug") or "")
            if slug and s != slug:
                continue
            bucket = by_slug.setdefault(
                s or "(unknown)",
                {"slug": s or "(unknown)", "lists": 0, "calls": 0, "denials": 0, "errors": 0, "agent_calls": 0, "dur": []},
            )
            et = ev.get("event_type")
            if et == "tools_list":
                bucket["lists"] += 1
            elif et == "tools_call":
                bucket["calls"] += 1
                name = str(ev.get("tool_name") or "")
                if name.startswith("agent__"):
                    bucket["agent_calls"] += 1
            if ev.get("phase") == "denied":
                bucket["denials"] += 1
            if ev.get("phase") == "error":
                bucket["errors"] += 1
            if ev.get("duration_ms") is not None:
                try:
                    bucket["dur"].append(float(ev["duration_ms"]))
                except (TypeError, ValueError):
                    pass
        clients = []
        for b in by_slug.values():
            durs = b.pop("dur")
            clients.append(
                {
                    **{k: b[k] for k in ("slug", "lists", "calls", "denials", "errors", "agent_calls")},
                    "avg_duration_ms": round(sum(durs) / len(durs), 1) if durs else 0.0,
                }
            )
        clients.sort(key=lambda c: (-c["calls"], -c["lists"]))
        active = 0
        for row in clients_map.values():
            if not isinstance(row, dict):
                continue
            ts = str(row.get("last_seen_at") or "")
            try:
                seen = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                continue
            if seen >= cutoff:
                active += 1
        return {
            "hours": hours,
            "active_clients": active,
            "clients": clients,
            "totals": {
                "lists": sum(c["lists"] for c in clients),
                "calls": sum(c["calls"] for c in clients),
                "denials": sum(c["denials"] for c in clients),
                "errors": sum(c["errors"] for c in clients),
                "agent_calls": sum(c["agent_calls"] for c in clients),
            },
        }

    def analytics_tools(self, *, hours: int = 24, slug: str | None = None) -> dict[str, Any]:
        from datetime import timedelta

        hours = max(1, min(int(hours or 24), 24 * 90))
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        with _lock:
            events = list(_load().get("telemetry") or [])
        agg: dict[tuple[str, str], dict[str, Any]] = {}
        for ev in events:
            if not isinstance(ev, dict) or ev.get("event_type") != "tools_call":
                continue
            ts = str(ev.get("occurred_at") or "")
            try:
                occurred = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                continue
            if occurred < cutoff:
                continue
            s = str(ev.get("mcp_client_slug") or "")
            if slug and s != slug:
                continue
            tool = str(ev.get("tool_name") or "")
            key = (tool, s or "(unknown)")
            bucket = agg.setdefault(
                key,
                {"tool_name": tool, "slug": s or "(unknown)", "calls": 0, "denials": 0, "errors": 0, "dur": []},
            )
            bucket["calls"] += 1
            if ev.get("phase") == "denied":
                bucket["denials"] += 1
            if ev.get("phase") == "error":
                bucket["errors"] += 1
            if ev.get("duration_ms") is not None:
                try:
                    bucket["dur"].append(float(ev["duration_ms"]))
                except (TypeError, ValueError):
                    pass
        tools = []
        for b in agg.values():
            durs = b.pop("dur")
            tools.append(
                {
                    "tool_name": b["tool_name"],
                    "slug": b["slug"],
                    "calls": b["calls"],
                    "denials": b["denials"],
                    "errors": b["errors"],
                    "avg_duration_ms": round(sum(durs) / len(durs), 1) if durs else 0.0,
                }
            )
        tools.sort(key=lambda t: -t["calls"])
        return {"hours": hours, "tools": tools[:100]}

    def analytics_errors(
        self,
        *,
        hours: int = 24,
        slug: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        from datetime import timedelta

        hours = max(1, min(int(hours or 24), 24 * 90))
        limit = max(1, min(int(limit or 100), 500))
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        with _lock:
            events = list(_load().get("telemetry") or [])
        filtered: list[dict[str, Any]] = []
        code_counts: dict[tuple[str, str], int] = {}
        for ev in events:
            if not isinstance(ev, dict):
                continue
            phase = str(ev.get("phase") or "")
            if phase not in ("error", "denied"):
                continue
            ts = str(ev.get("occurred_at") or "")
            try:
                occurred = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                continue
            if occurred < cutoff:
                continue
            s = str(ev.get("mcp_client_slug") or "")
            if slug and s != slug:
                continue
            code = str(ev.get("error_code") or "") or "(none)"
            code_counts[(code, phase)] = code_counts.get((code, phase), 0) + 1
            filtered.append(ev)
        filtered.sort(key=lambda e: str(e.get("occurred_at") or ""), reverse=True)
        by_code = [
            {"error_code": code, "phase": phase, "count": n}
            for (code, phase), n in sorted(code_counts.items(), key=lambda kv: -kv[1])[:50]
        ]
        out = []
        for ev in filtered[:limit]:
            dur = ev.get("duration_ms")
            try:
                duration_ms = int(dur) if dur is not None else None
            except (TypeError, ValueError):
                duration_ms = None
            sid = ev.get("server_id")
            try:
                server_id = int(sid) if sid is not None else None
            except (TypeError, ValueError):
                server_id = None
            out.append(
                {
                    "occurred_at": str(ev.get("occurred_at") or ""),
                    "event_type": ev.get("event_type"),
                    "slug": str(ev.get("mcp_client_slug") or "") or "(unknown)",
                    "tool_name": ev.get("tool_name") or None,
                    "original_tool": ev.get("original_tool"),
                    "server_id": server_id,
                    "phase": ev.get("phase"),
                    "error_code": ev.get("error_code"),
                    "reason": (
                        str((ev.get("meta") or {}).get("reason") or "").strip() or None
                        if isinstance(ev.get("meta"), dict)
                        else None
                    ),
                    "duration_ms": duration_ms,
                    "request_id": ev.get("request_id"),
                }
            )
        return {"hours": hours, "limit": limit, "by_code": by_code, "events": out}
