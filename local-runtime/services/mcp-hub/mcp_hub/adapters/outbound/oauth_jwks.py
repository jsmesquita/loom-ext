"""OAuth access-token validation for the MCP Hub resource (ADR 0011 / specs 017, 024)."""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any

import jwt
from jwt import PyJWKClient

from mcp_hub.domain.records import HubIdentity

logger = logging.getLogger("mcp_hub.oauth")

_jwks_client: PyJWKClient | None = None
_jwks_url_cached: str | None = None


def resource_url() -> str:
    import os

    return os.environ.get("MCP_HUB_RESOURCE", "http://127.0.0.1:8790/mcp").rstrip("/")


def oidc_issuer() -> str:
    import os

    return os.environ.get("MCP_HUB_OIDC_ISSUER", "").rstrip("/")


def oidc_audience() -> str:
    import os

    return os.environ.get("MCP_HUB_OIDC_AUDIENCE", "loom-mcp-hub").strip()


def oidc_jwks_url() -> str:
    import os

    explicit = os.environ.get("MCP_HUB_OIDC_JWKS_URL", "").strip()
    if explicit:
        return explicit
    issuer = oidc_issuer()
    if not issuer:
        return ""
    return f"{issuer}/protocol/openid-connect/certs"


def prm_document() -> dict[str, Any]:
    import os

    issuer = oidc_issuer()
    resource = resource_url()
    meta_base = os.environ.get("MCP_HUB_PUBLIC_BASE", "http://127.0.0.1:8790").rstrip("/")
    return {
        "resource": resource,
        "authorization_servers": [issuer] if issuer else [],
        "scopes_supported": ["openid", "profile"],
        "bearer_methods_supported": ["header"],
        "resource_documentation": f"{meta_base}/",
    }


def www_authenticate_value() -> str:
    import os

    meta_base = os.environ.get("MCP_HUB_PUBLIC_BASE", "http://127.0.0.1:8790").rstrip("/")
    meta = f"{meta_base}/.well-known/oauth-protected-resource"
    return f'Bearer realm="loom-mcp-hub", resource_metadata="{meta}"'


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client, _jwks_url_cached
    url = oidc_jwks_url()
    if not url:
        raise ValueError("jwks_url_unset")
    if _jwks_client is None or _jwks_url_cached != url:
        _jwks_client = PyJWKClient(url, cache_keys=True, lifespan=3600)
        _jwks_url_cached = url
    return _jwks_client


def _claim_audiences(claims: dict[str, Any]) -> list[str]:
    aud = claims.get("aud")
    if isinstance(aud, str):
        return [aud]
    if isinstance(aud, list):
        return [str(a) for a in aud]
    return []


def _audiences_ok(claims: dict[str, Any]) -> bool:
    expected_aud = oidc_audience()
    expected_resource = resource_url()
    auds = _claim_audiences(claims)
    if expected_aud and expected_aud in auds:
        return True
    if expected_resource and expected_resource in auds:
        return True
    # Some AS put resource indicator in a dedicated claim.
    for key in ("resource", "rsc"):
        val = claims.get(key)
        if val == expected_resource:
            return True
        if isinstance(val, list) and expected_resource in val:
            return True
    azp = str(claims.get("azp") or "")
    if expected_aud and azp == expected_aud:
        return True
    return False


def admin_audiences() -> list[str]:
    """Audiences accepted for Hub ops admin (/v1/*) from the Loom SPA JWT."""
    import os

    raw = os.environ.get(
        "MCP_HUB_ADMIN_AUDIENCES",
        "loom-frontend,loom-mcp-hub",
    )
    out = [p.strip() for p in raw.split(",") if p.strip()]
    resource = resource_url()
    if resource and resource not in out:
        out.append(resource)
    return out


def _admin_audiences_ok(claims: dict[str, Any]) -> bool:
    allowed = set(admin_audiences())
    auds = set(_claim_audiences(claims))
    if auds & allowed:
        return True
    azp = str(claims.get("azp") or "")
    return bool(azp and azp in allowed)


def _extract_groups(claims: dict[str, Any]) -> list[str]:
    raw = claims.get("groups")
    if isinstance(raw, list):
        return [str(g) for g in raw if g]
    realm = claims.get("realm_access")
    if isinstance(realm, dict):
        roles = realm.get("roles")
        if isinstance(roles, list):
            return [str(g) for g in roles if g]
    return []


def _decode_claims(token: str) -> dict[str, Any] | None:
    if not token:
        return None
    if token.startswith("hs_"):
        logger.info("rejected_legacy_hub_session_token")
        return None
    issuer = oidc_issuer()
    if not issuer:
        logger.error("MCP_HUB_OIDC_ISSUER unset — fail-closed")
        return None
    try:
        jwks = _get_jwks_client()
        signing_key = jwks.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            issuer=issuer,
            options={
                "require": ["exp", "iss", "sub"],
                "verify_aud": False,  # checked explicitly for resource/client aud
            },
            leeway=30,
        )
    except Exception as exc:
        logger.info("jwt_validation_failed: %s", type(exc).__name__)
        return None


def _identity_from_claims(claims: dict[str, Any], token: str) -> HubIdentity | None:
    sub = str(claims.get("sub") or "").strip()
    if not sub:
        return None
    username = str(claims.get("preferred_username") or claims.get("email") or sub)
    return {
        "sub": sub,
        "username": username,
        "groups": _extract_groups(claims),
        "connection_id": f"oauth:{sub}",
        "access_token": token,
    }


def validate_access_token(token: str) -> HubIdentity | None:
    """Return identity for MCP resource (IDE) — aud must be Hub client/resource."""
    claims = _decode_claims(token)
    if claims is None:
        return None
    if not _audiences_ok(claims):
        logger.info("jwt_audience_rejected aud=%s azp=%s", claims.get("aud"), claims.get("azp"))
        return None
    return _identity_from_claims(claims, token)


def validate_admin_token(token: str) -> HubIdentity | None:
    """Return identity for Hub ops (/v1/*) — accepts SPA aud (loom-frontend) too."""
    claims = _decode_claims(token)
    if claims is None:
        return None
    if not _admin_audiences_ok(claims):
        logger.info(
            "jwt_admin_audience_rejected aud=%s azp=%s",
            claims.get("aud"),
            claims.get("azp"),
        )
        return None
    return _identity_from_claims(claims, token)


def warm_jwks() -> bool:
    """Best-effort JWKS fetch at startup; returns False if unreachable."""
    url = oidc_jwks_url()
    if not url:
        return False
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return bool(data.get("keys"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return False


class OAuthJwksValidator:
    """Outbound adapter implementing ``TokenValidator``."""

    def validate_access_token(self, token: str) -> HubIdentity | None:
        return validate_access_token(token)

    def validate_admin_token(self, token: str) -> HubIdentity | None:
        return validate_admin_token(token)

    def www_authenticate_value(self) -> str:
        return www_authenticate_value()

    def resource_url(self) -> str:
        return resource_url()

    def oidc_issuer(self) -> str:
        return oidc_issuer()

    def warm_jwks(self) -> bool:
        return warm_jwks()

    def prm_document(self) -> dict[str, Any]:
        return prm_document()
