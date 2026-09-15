"""Postgres HubStore adapter (dedicated DB ``mcp_hub``)."""
from __future__ import annotations

import json
import logging
import os
import threading
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse, urlunparse

from mcp_hub.domain.client_records import client_summary, normalize_grant, refresh_allowed_groups

logger = logging.getLogger("mcp_hub.pg_store")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS hub_clients (
    slug TEXT PRIMARY KEY,
    display_name TEXT NOT NULL DEFAULT '',
    declared_name TEXT NOT NULL DEFAULT '',
    declared_version TEXT NOT NULL DEFAULT '',
    declared_family TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'discovered',
    agents_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    grants JSONB NOT NULL DEFAULT '[]'::jsonb,
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS hub_session_bindings (
    hub_session_id TEXT PRIMARY KEY,
    mcp_client_slug TEXT NOT NULL REFERENCES hub_clients(slug) ON DELETE CASCADE,
    bound_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS hub_telemetry_events (
    id BIGSERIAL PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    event_type TEXT NOT NULL,
    request_id TEXT NOT NULL,
    hub_session_id TEXT,
    mcp_client_slug TEXT,
    subject_hash TEXT,
    idp_groups JSONB NOT NULL DEFAULT '[]'::jsonb,
    tool_name TEXT,
    original_tool TEXT,
    server_id INT,
    phase TEXT,
    error_code TEXT,
    duration_ms INT,
    meta JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS hub_clients_status_idx ON hub_clients (status);
CREATE INDEX IF NOT EXISTS hub_clients_last_seen_idx ON hub_clients (last_seen_at);
CREATE INDEX IF NOT EXISTS hub_telemetry_occurred_idx ON hub_telemetry_events (occurred_at DESC);
CREATE INDEX IF NOT EXISTS hub_telemetry_slug_idx ON hub_telemetry_events (mcp_client_slug, occurred_at DESC);
CREATE INDEX IF NOT EXISTS hub_telemetry_type_idx ON hub_telemetry_events (event_type, occurred_at DESC);
"""


def database_url() -> str:
    return os.environ.get("MCP_HUB_DATABASE_URL", "").strip()


def _normalize_dsn(url: str) -> str:
    """Accept SQLAlchemy-style URLs and plain postgres:// for psycopg."""
    raw = url.strip()
    for prefix in ("postgresql+psycopg2://", "postgresql+psycopg://"):
        if raw.startswith(prefix):
            return "postgresql://" + raw[len(prefix) :]
    return raw


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str:
    if dt is None:
        return _now().isoformat().replace("+00:00", "Z")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _row_to_client(row: Any, *, include_grants: bool) -> dict[str, Any]:
    grants = row["grants"]
    if isinstance(grants, str):
        grants = json.loads(grants)
    if not isinstance(grants, list):
        grants = []
    full = {
        "slug": row["slug"],
        "display_name": row["display_name"],
        "declared_name": row["declared_name"],
        "declared_version": row["declared_version"],
        "declared_family": row["declared_family"],
        "status": row["status"],
        "agents_enabled": bool(row["agents_enabled"]),
        "grants": grants,
        "first_seen_at": _iso(row["first_seen_at"]),
        "last_seen_at": _iso(row["last_seen_at"]),
    }
    refresh_allowed_groups(full)
    if include_grants:
        return full
    return client_summary(full)


class PostgresHubStore:
    """Outbound adapter implementing ``HubStore`` against PostgreSQL."""

    def __init__(self, dsn: str | None = None) -> None:
        import psycopg
        from psycopg.rows import dict_row
        from psycopg.types.json import Json

        self._psycopg = psycopg
        self._dict_row = dict_row
        self._Json = Json
        self._dsn = _normalize_dsn(dsn or database_url())
        if not self._dsn:
            raise ValueError("MCP_HUB_DATABASE_URL unset")
        self._lock = threading.RLock()
        self._ensure_schema()

    def store_path(self) -> str:
        # Observability: surface DSN host/db without password
        try:
            parsed = urlparse(self._dsn)
            safe = parsed._replace(netloc=f"{parsed.hostname}:{parsed.port or 5432}")
            return urlunparse(safe)
        except Exception:
            return "postgresql://***"

    def _connect(self):
        return self._psycopg.connect(self._dsn, row_factory=self._dict_row)

    def _ensure_schema(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(_SCHEMA)
                conn.commit()
        logger.info("hub postgres schema ready dsn=%s", self.store_path())

    def list_clients(self, status: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            with self._connect() as conn:
                if status:
                    rows = conn.execute(
                        "SELECT * FROM hub_clients WHERE status = %s "
                        "ORDER BY COALESCE(last_seen_at, first_seen_at)",
                        (status,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM hub_clients "
                        "ORDER BY COALESCE(last_seen_at, first_seen_at)"
                    ).fetchall()
        return [_row_to_client(r, include_grants=False) for r in rows]

    def get_client(self, slug: str, *, include_grants: bool = False) -> dict[str, Any] | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT * FROM hub_clients WHERE slug = %s", (slug,)
                ).fetchone()
        if row is None:
            return None
        return _row_to_client(row, include_grants=include_grants)

    def get_profile_grants(self, slug: str, group: str) -> dict[str, Any] | None:
        group = str(group or "").strip()
        if not group:
            return None
        client = self.get_client(slug, include_grants=True)
        if client is None:
            return None
        grants = [
            deepcopy(g)
            for g in (client.get("grants") or [])
            if str(g.get("group") or "") == group
        ]
        return {"slug": slug, "group": group, "grants": grants}

    def put_profile_grants(
        self, slug: str, group: str, grants: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        group = str(group or "").strip()
        if not group:
            return None
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT grants FROM hub_clients WHERE slug = %s FOR UPDATE", (slug,)
                ).fetchone()
                if row is None:
                    return None
                existing = row["grants"]
                if isinstance(existing, str):
                    existing = json.loads(existing)
                if not isinstance(existing, list):
                    existing = []
                kept = [g for g in existing if str(g.get("group") or "") != group]
                cleaned: list[dict[str, Any]] = []
                for g in grants:
                    item = normalize_grant(g, group=group)
                    if item is not None:
                        cleaned.append(item)
                merged = kept + cleaned
                conn.execute(
                    "UPDATE hub_clients SET grants = %s WHERE slug = %s",
                    (self._Json(merged), slug),
                )
                conn.commit()
        return {"slug": slug, "group": group, "grants": deepcopy(cleaned)}

    def put_grants(self, slug: str, grants: list[dict[str, Any]]) -> dict[str, Any] | None:
        cleaned: list[dict[str, Any]] = []
        for g in grants:
            group = str(g.get("group") or "").strip()
            if not group:
                continue
            item = normalize_grant(g, group=group)
            if item is not None:
                cleaned.append(item)
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    "UPDATE hub_clients SET grants = %s WHERE slug = %s RETURNING *",
                    (self._Json(cleaned), slug),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                conn.commit()
        return _row_to_client(row, include_grants=True)

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
        now = _now()
        display = display_name or declared_name or slug
        with self._lock:
            with self._connect() as conn:
                existing = conn.execute(
                    "SELECT * FROM hub_clients WHERE slug = %s FOR UPDATE", (slug,)
                ).fetchone()
                if existing is None:
                    conn.execute(
                        """
                        INSERT INTO hub_clients (
                            slug, display_name, declared_name, declared_version,
                            declared_family, status, agents_enabled, grants,
                            first_seen_at, last_seen_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, 'discovered', FALSE, '[]'::jsonb, %s, %s
                        )
                        """,
                        (
                            slug,
                            display,
                            declared_name,
                            declared_version,
                            declared_family,
                            now,
                            now,
                        ),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE hub_clients SET
                            declared_name = %s,
                            declared_version = %s,
                            declared_family = %s,
                            last_seen_at = %s,
                            display_name = CASE
                                WHEN display_name IS NULL OR display_name = '' THEN %s
                                ELSE display_name
                            END
                        WHERE slug = %s
                        """,
                        (
                            declared_name,
                            declared_version,
                            declared_family,
                            now,
                            display,
                            slug,
                        ),
                    )
                conn.execute(
                    """
                    INSERT INTO hub_session_bindings (hub_session_id, mcp_client_slug, bound_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (hub_session_id) DO UPDATE SET
                        mcp_client_slug = EXCLUDED.mcp_client_slug,
                        bound_at = EXCLUDED.bound_at
                    """,
                    (hub_session_id, slug, now),
                )
                row = conn.execute(
                    "SELECT * FROM hub_clients WHERE slug = %s", (slug,)
                ).fetchone()
                conn.commit()
        assert row is not None
        return _row_to_client(row, include_grants=True)

    def session_client_slug(self, hub_session_id: str) -> str | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT mcp_client_slug FROM hub_session_bindings WHERE hub_session_id = %s",
                    (hub_session_id,),
                ).fetchone()
        if row is None:
            return None
        slug = row.get("mcp_client_slug")
        return str(slug) if slug else None

    def patch_client(self, slug: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        sets: list[str] = []
        args: list[Any] = []
        if "status" in patch and patch["status"] in ("discovered", "enabled", "disabled"):
            sets.append("status = %s")
            args.append(patch["status"])
        if "display_name" in patch and isinstance(patch["display_name"], str):
            sets.append("display_name = %s")
            args.append(patch["display_name"][:128])
        if "agents_enabled" in patch:
            sets.append("agents_enabled = %s")
            args.append(bool(patch["agents_enabled"]))
        # allowed_groups is derived from grants; ignore write-through for PG
        if not sets:
            return self.get_client(slug, include_grants=True)
        args.append(slug)
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    f"UPDATE hub_clients SET {', '.join(sets)} WHERE slug = %s RETURNING *",
                    tuple(args),
                ).fetchone()
                if row is None:
                    return None
                conn.commit()
        return _row_to_client(row, include_grants=True)

    def delete_client(self, slug: str) -> bool:
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute("DELETE FROM hub_clients WHERE slug = %s", (slug,))
                deleted = cur.rowcount > 0
                conn.commit()
        return deleted

    def client_count(self) -> int:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT COUNT(*) AS n FROM hub_clients").fetchone()
        return int(row["n"] if row else 0)

    def import_snapshot(self, data: dict[str, Any]) -> int:
        """Import JSON hub_clients snapshot. Returns number of clients written."""
        clients = data.get("clients") or {}
        bindings = data.get("session_bindings") or {}
        if not isinstance(clients, dict):
            return 0
        count = 0
        with self._lock:
            with self._connect() as conn:
                for slug, row in clients.items():
                    if not isinstance(row, dict):
                        continue
                    grants = row.get("grants") or []
                    if not isinstance(grants, list):
                        grants = []
                    first = row.get("first_seen_at") or _iso(_now())
                    last = row.get("last_seen_at") or first
                    conn.execute(
                        """
                        INSERT INTO hub_clients (
                            slug, display_name, declared_name, declared_version,
                            declared_family, status, agents_enabled, grants,
                            first_seen_at, last_seen_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s,
                            %s::timestamptz, %s::timestamptz
                        )
                        ON CONFLICT (slug) DO UPDATE SET
                            display_name = EXCLUDED.display_name,
                            declared_name = EXCLUDED.declared_name,
                            declared_version = EXCLUDED.declared_version,
                            declared_family = EXCLUDED.declared_family,
                            status = EXCLUDED.status,
                            agents_enabled = EXCLUDED.agents_enabled,
                            grants = EXCLUDED.grants,
                            last_seen_at = EXCLUDED.last_seen_at
                        """,
                        (
                            str(slug),
                            str(row.get("display_name") or slug)[:128],
                            str(row.get("declared_name") or ""),
                            str(row.get("declared_version") or ""),
                            str(row.get("declared_family") or ""),
                            str(row.get("status") or "discovered"),
                            bool(row.get("agents_enabled", False)),
                            self._Json(grants),
                            first,
                            last,
                        ),
                    )
                    count += 1
                if isinstance(bindings, dict):
                    for sid, bind in bindings.items():
                        if not isinstance(bind, dict):
                            continue
                        cslug = bind.get("mcp_client_slug")
                        if not cslug:
                            continue
                        # skip orphan bindings
                        exists = conn.execute(
                            "SELECT 1 FROM hub_clients WHERE slug = %s", (str(cslug),)
                        ).fetchone()
                        if not exists:
                            continue
                        bound = bind.get("bound_at") or _iso(_now())
                        conn.execute(
                            """
                            INSERT INTO hub_session_bindings (hub_session_id, mcp_client_slug, bound_at)
                            VALUES (%s, %s, %s::timestamptz)
                            ON CONFLICT (hub_session_id) DO UPDATE SET
                                mcp_client_slug = EXCLUDED.mcp_client_slug,
                                bound_at = EXCLUDED.bound_at
                            """,
                            (str(sid), str(cslug), bound),
                        )
                conn.commit()
        return count

    def touch_last_seen(self, slug: str) -> None:
        if not slug:
            return
        try:
            with self._lock:
                with self._connect() as conn:
                    conn.execute(
                        "UPDATE hub_clients SET last_seen_at = %s WHERE slug = %s",
                        (_now(), slug),
                    )
                    conn.commit()
        except Exception:
            logger.warning("touch_last_seen failed slug=%s", slug, exc_info=True)

    def record_telemetry(self, event: dict[str, Any]) -> None:
        try:
            with self._lock:
                with self._connect() as conn:
                    conn.execute(
                        """
                        INSERT INTO hub_telemetry_events (
                            event_type, request_id, hub_session_id, mcp_client_slug,
                            subject_hash, idp_groups, tool_name, original_tool,
                            server_id, phase, error_code, duration_ms, meta
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        """,
                        (
                            str(event.get("event_type") or "unknown"),
                            str(event.get("request_id") or ""),
                            event.get("hub_session_id"),
                            event.get("mcp_client_slug"),
                            event.get("subject_hash"),
                            self._Json(list(event.get("idp_groups") or [])),
                            event.get("tool_name"),
                            event.get("original_tool"),
                            event.get("server_id"),
                            event.get("phase"),
                            event.get("error_code"),
                            event.get("duration_ms"),
                            self._Json(dict(event.get("meta") or {})),
                        ),
                    )
                    conn.commit()
        except Exception:
            logger.warning("record_telemetry failed", exc_info=True)

    def analytics_summary(self, *, hours: int = 24, slug: str | None = None) -> dict[str, Any]:
        hours = max(1, min(int(hours or 24), 24 * 90))
        params: list[Any] = [hours]
        where = "occurred_at >= now() - (%s || ' hours')::interval"
        if slug:
            where += " AND mcp_client_slug = %s"
            params.append(slug)
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    f"""
                    SELECT
                      COALESCE(mcp_client_slug, '') AS slug,
                      COUNT(*) FILTER (WHERE event_type = 'tools_list') AS lists,
                      COUNT(*) FILTER (WHERE event_type = 'tools_call') AS calls,
                      COUNT(*) FILTER (WHERE phase = 'denied') AS denials,
                      COUNT(*) FILTER (WHERE phase = 'error') AS errors,
                      COUNT(*) FILTER (
                        WHERE event_type = 'tools_call' AND tool_name LIKE 'agent__%%'
                      ) AS agent_calls,
                      COALESCE(AVG(duration_ms) FILTER (WHERE duration_ms IS NOT NULL), 0) AS avg_ms
                    FROM hub_telemetry_events
                    WHERE {where}
                    GROUP BY 1
                    ORDER BY calls DESC, lists DESC
                    """,
                    tuple(params),
                ).fetchall()
                active = conn.execute(
                    """
                    SELECT COUNT(*) AS n FROM hub_clients
                    WHERE last_seen_at >= now() - (%s || ' hours')::interval
                    """,
                    (hours,),
                ).fetchone()
        clients = [
            {
                "slug": r["slug"] or "(unknown)",
                "lists": int(r["lists"] or 0),
                "calls": int(r["calls"] or 0),
                "denials": int(r["denials"] or 0),
                "errors": int(r["errors"] or 0),
                "agent_calls": int(r["agent_calls"] or 0),
                "avg_duration_ms": round(float(r["avg_ms"] or 0), 1),
            }
            for r in rows
        ]
        return {
            "hours": hours,
            "active_clients": int(active["n"] if active else 0),
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
        hours = max(1, min(int(hours or 24), 24 * 90))
        params: list[Any] = [hours]
        where = "occurred_at >= now() - (%s || ' hours')::interval AND event_type = 'tools_call'"
        if slug:
            where += " AND mcp_client_slug = %s"
            params.append(slug)
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    f"""
                    SELECT
                      COALESCE(tool_name, '') AS tool_name,
                      COALESCE(mcp_client_slug, '') AS slug,
                      COUNT(*) AS calls,
                      COUNT(*) FILTER (WHERE phase = 'denied') AS denials,
                      COUNT(*) FILTER (WHERE phase = 'error') AS errors,
                      COALESCE(AVG(duration_ms) FILTER (WHERE duration_ms IS NOT NULL), 0) AS avg_ms
                    FROM hub_telemetry_events
                    WHERE {where}
                    GROUP BY 1, 2
                    ORDER BY calls DESC
                    LIMIT 100
                    """,
                    tuple(params),
                ).fetchall()
        return {
            "hours": hours,
            "tools": [
                {
                    "tool_name": r["tool_name"],
                    "slug": r["slug"] or "(unknown)",
                    "calls": int(r["calls"] or 0),
                    "denials": int(r["denials"] or 0),
                    "errors": int(r["errors"] or 0),
                    "avg_duration_ms": round(float(r["avg_ms"] or 0), 1),
                }
                for r in rows
            ],
        }

    def analytics_errors(
        self,
        *,
        hours: int = 24,
        slug: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        hours = max(1, min(int(hours or 24), 24 * 90))
        limit = max(1, min(int(limit or 100), 500))
        params: list[Any] = [hours]
        where = (
            "occurred_at >= now() - (%s || ' hours')::interval "
            "AND phase IN ('error', 'denied')"
        )
        if slug:
            where += " AND mcp_client_slug = %s"
            params.append(slug)
        params.append(limit)
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    f"""
                    SELECT
                      occurred_at,
                      event_type,
                      COALESCE(mcp_client_slug, '') AS slug,
                      COALESCE(tool_name, '') AS tool_name,
                      original_tool,
                      server_id,
                      phase,
                      error_code,
                      duration_ms,
                      request_id,
                      COALESCE(meta->>'reason', '') AS reason
                    FROM hub_telemetry_events
                    WHERE {where}
                    ORDER BY occurred_at DESC
                    LIMIT %s
                    """,
                    tuple(params),
                ).fetchall()
                by_code = conn.execute(
                    f"""
                    SELECT
                      COALESCE(NULLIF(error_code, ''), '(none)') AS error_code,
                      phase,
                      COUNT(*) AS n
                    FROM hub_telemetry_events
                    WHERE {where}
                    GROUP BY 1, 2
                    ORDER BY n DESC
                    LIMIT 50
                    """,
                    tuple(params[:-1]),
                ).fetchall()
        return {
            "hours": hours,
            "limit": limit,
            "by_code": [
                {
                    "error_code": r["error_code"],
                    "phase": r["phase"],
                    "count": int(r["n"] or 0),
                }
                for r in by_code
            ],
            "events": [
                {
                    "occurred_at": r["occurred_at"].isoformat()
                    if hasattr(r["occurred_at"], "isoformat")
                    else str(r["occurred_at"] or ""),
                    "event_type": r["event_type"],
                    "slug": r["slug"] or "(unknown)",
                    "tool_name": r["tool_name"] or None,
                    "original_tool": r["original_tool"],
                    "server_id": int(r["server_id"]) if r["server_id"] is not None else None,
                    "phase": r["phase"],
                    "error_code": r["error_code"],
                    "reason": (r["reason"] or None) or None,
                    "duration_ms": int(r["duration_ms"]) if r["duration_ms"] is not None else None,
                    "request_id": r["request_id"],
                }
                for r in rows
            ],
        }
