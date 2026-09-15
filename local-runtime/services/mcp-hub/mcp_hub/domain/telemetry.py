"""Hub telemetry helpers (Spec 028) — subject hash + event shape."""
from __future__ import annotations

import hashlib
import uuid
from typing import Any


def subject_hash(subject: str | None) -> str:
    raw = (subject or "").strip()
    if not raw:
        return ""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def new_request_id() -> str:
    return str(uuid.uuid4())


def safe_error_reason(value: Any, *, max_len: int = 280) -> str:
    """Short operational reason for analytics — never args/prompt/response bodies."""
    if value is None:
        return ""
    if isinstance(value, dict):
        for key in ("message", "error", "detail", "reason"):
            if value.get(key) not in (None, ""):
                value = value[key]
                break
        else:
            value = str(value)
    text = " ".join(str(value).split())
    # Redact obvious bearer/token fragments if a child echoed them.
    lowered = text.lower()
    for needle in ("bearer ", "token-", "api_key=", "authorization:"):
        idx = lowered.find(needle)
        if idx >= 0:
            text = text[:idx] + "[redacted]"
            break
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def telemetry_event(
    *,
    event_type: str,
    request_id: str | None = None,
    hub_session_id: str | None = None,
    mcp_client_slug: str | None = None,
    subject: str | None = None,
    groups: list[str] | None = None,
    tool_name: str | None = None,
    original_tool: str | None = None,
    server_id: int | None = None,
    phase: str | None = None,
    error_code: str | None = None,
    duration_ms: int | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "request_id": request_id or new_request_id(),
        "hub_session_id": hub_session_id,
        "mcp_client_slug": mcp_client_slug,
        "subject_hash": subject_hash(subject),
        "idp_groups": list(groups or []),
        "tool_name": tool_name,
        "original_tool": original_tool,
        "server_id": server_id,
        "phase": phase,
        "error_code": error_code,
        "duration_ms": duration_ms,
        "meta": dict(meta or {}),
    }
