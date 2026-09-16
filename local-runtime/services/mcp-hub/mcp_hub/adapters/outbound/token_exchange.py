"""Resolve a Loom API access token from the Hub OAuth token (ADR 0015).

Modes:
- ``dual_aud`` (default): Hub token also carries ``loom-frontend`` audience
  (Keycloak mapper). Reuse Token H as Token L.
- ``exchange``: RFC 8693 token exchange when
  ``LOOM_TOKEN_EXCHANGE_CLIENT_ID`` (+ secret) are set.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger("mcp_hub.token_exchange")

_cache_lock = threading.Lock()
_cache: dict[str, tuple[str, float]] = {}


def exchange_mode() -> str:
    if os.environ.get("LOOM_TOKEN_EXCHANGE_CLIENT_ID", "").strip():
        return "exchange"
    return os.environ.get("LOOM_ACCESS_TOKEN_MODE", "dual_aud").strip().lower() or "dual_aud"


def _token_endpoint() -> str:
    explicit = os.environ.get("LOOM_OIDC_TOKEN_URL", "").strip()
    if explicit:
        return explicit
    issuer = os.environ.get("MCP_HUB_OIDC_ISSUER", "").rstrip("/")
    if not issuer:
        return ""
    return f"{issuer}/protocol/openid-connect/token"


def _exchange(subject_token: str) -> str | None:
    token_url = _token_endpoint()
    client_id = os.environ.get("LOOM_TOKEN_EXCHANGE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("LOOM_TOKEN_EXCHANGE_CLIENT_SECRET", "").strip()
    audience = os.environ.get("LOOM_TOKEN_EXCHANGE_AUDIENCE", "loom-frontend").strip()
    if not token_url or not client_id:
        return None
    body = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "client_id": client_id,
        "client_secret": client_secret,
        "subject_token": subject_token,
        "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
        "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
        "audience": audience,
    }).encode("utf-8")
    req = urllib.request.Request(
        token_url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8") or "{}")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        logger.warning("token_exchange_failed: %s", type(exc).__name__)
        return None
    access = payload.get("access_token")
    if not isinstance(access, str) or not access:
        return None
    expires_in = int(payload.get("expires_in") or 60)
    with _cache_lock:
        _cache[subject_token[-32:]] = (access, time.time() + max(30, expires_in - 30))
    return access


def loom_api_token(hub_access_token: str) -> str | None:
    """Return a bearer suitable for Loom ``/api/*``, or None."""
    token = (hub_access_token or "").strip()
    if not token:
        return None
    mode = exchange_mode()
    if mode == "exchange":
        key = token[-32:]
        with _cache_lock:
            hit = _cache.get(key)
            if hit and hit[1] > time.time():
                return hit[0]
        exchanged = _exchange(token)
        return exchanged
    # dual_aud interim: same JWT accepted by Hub (aud hub) and Loom (aud frontend)
    return token
