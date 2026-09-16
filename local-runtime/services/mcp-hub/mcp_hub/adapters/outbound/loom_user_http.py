"""HTTP client to Loom BFF using the user JWT (ADR 0015)."""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

from mcp_hub.adapters.outbound.token_exchange import loom_api_token

logger = logging.getLogger("mcp_hub.loom_user_http")


def loom_base() -> str:
    return os.environ.get("LOOM_BACKEND_URL", "http://backend:8000").rstrip("/")


def _request(
    method: str,
    path: str,
    *,
    access_token: str,
    body: dict[str, Any] | None = None,
    timeout: float = 60,
    accept: str = "application/json",
) -> tuple[int, Any]:
    api_token = loom_api_token(access_token)
    if not api_token:
        return 401, {"detail": "loom_token_unavailable"}
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{loom_base()}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
            "Accept": accept,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8") or ""
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8") or ""
        status = exc.code
        content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
    except Exception as exc:
        logger.warning("loom_unreachable: %s", type(exc).__name__)
        return 502, {"detail": "loom_unreachable"}

    if "text/event-stream" in content_type or accept == "text/event-stream":
        return status, raw
    if not raw:
        return status, {}
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return status, {"detail": "invalid_json", "raw": raw[:200]}


def loom_get(path: str, *, access_token: str, timeout: float = 30) -> tuple[int, Any]:
    return _request("GET", path, access_token=access_token, timeout=timeout)


def loom_post(
    path: str,
    body: dict[str, Any] | None,
    *,
    access_token: str,
    timeout: float = 60,
    accept: str = "application/json",
) -> tuple[int, Any]:
    return _request(
        "POST",
        path,
        access_token=access_token,
        body=body,
        timeout=timeout,
        accept=accept,
    )
