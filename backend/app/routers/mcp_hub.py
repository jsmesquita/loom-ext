"""MCP Hub BFF — ops/plugin only (ADR 0015 phase 5).

Data-plane (materialize / tools/call / agents) lives in the Hub sidecar.
This module keeps:
- public ``/api/mcp/hub/info`` (IDE OAuth resource URL)
- ``/api/ext/local-runtime/*`` proxy to Hub admin APIs (service token Hub↔BFF)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies.auth import UserInfo, require_scopes
from app.services import mcp_hub as hub
from app.services import mcp_hub_proxy as hub_proxy

router = APIRouter(prefix="/api/mcp/hub", tags=["mcp-hub"])
ext_router = APIRouter(prefix="/api/ext/local-runtime", tags=["local-runtime-ext"])


class ClientPatchRequest(BaseModel):
    status: str | None = None
    display_name: str | None = None
    allowed_groups: list[str] | None = None
    agents_enabled: bool | None = None


class ClientGrantsRequest(BaseModel):
    group: str = Field(..., min_length=1, max_length=128)
    grants: list[dict[str, Any]] = Field(default_factory=list)


@router.get("/info")
def hub_public_info() -> dict:
    """Public Hub resource URL for IDE OAuth."""
    return {
        "mcp_hub_url": hub.hub_public_url(),
        "resource": hub.hub_public_url(),
        "auth": "oauth",
        "contract_version": hub.CONTRACT_VERSION,
    }


@ext_router.get("/mcp-clients")
def list_mcp_clients(
    status_filter: str | None = Query(default=None, alias="status"),
    user: UserInfo = Depends(require_scopes("mcp:read")),
) -> dict:
    _ = user
    code, payload = hub_proxy.list_clients(status_filter)
    if code >= 400:
        raise HTTPException(status_code=code, detail=payload.get("error") or payload.get("detail") or "hub_error")
    return payload


@ext_router.get("/mcp-clients/{slug}/profile-grants")
def get_mcp_client_profile_grants(
    slug: str,
    group: str = Query(..., min_length=1, max_length=128),
    user: UserInfo = Depends(require_scopes("mcp:read")),
) -> dict:
    """On-demand grants for one IdP profile. Empty profile → 200 + grants=[]."""
    _ = user
    code, payload = hub_proxy.get_profile_grants(slug, group)
    if code >= 400:
        raise HTTPException(status_code=code, detail=payload.get("error") or payload.get("detail") or "hub_error")
    return payload


@ext_router.put("/mcp-clients/{slug}/profile-grants")
def put_mcp_client_grants(
    slug: str,
    body: ClientGrantsRequest,
    user: UserInfo = Depends(require_scopes("mcp:write")),
) -> dict:
    _ = user
    code, payload = hub_proxy.put_grants(slug, body.grants, group=body.group)
    if code >= 400:
        raise HTTPException(status_code=code, detail=payload.get("error") or payload.get("detail") or "hub_error")
    return payload


@ext_router.get("/mcp-clients/{slug}")
def get_mcp_client(
    slug: str,
    user: UserInfo = Depends(require_scopes("mcp:read")),
) -> dict:
    _ = user
    code, payload = hub_proxy.get_client(slug)
    if code >= 400:
        raise HTTPException(status_code=code, detail=payload.get("error") or payload.get("detail") or "hub_error")
    return payload


@ext_router.patch("/mcp-clients/{slug}")
def patch_mcp_client(
    slug: str,
    body: ClientPatchRequest,
    user: UserInfo = Depends(require_scopes("mcp:write")),
) -> dict:
    _ = user
    code, payload = hub_proxy.patch_client(slug, body.model_dump(exclude_none=True))
    if code >= 400:
        raise HTTPException(status_code=code, detail=payload.get("error") or payload.get("detail") or "hub_error")
    return payload


@ext_router.delete("/mcp-clients/{slug}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mcp_client(
    slug: str,
    user: UserInfo = Depends(require_scopes("mcp:write")),
) -> None:
    _ = user
    code, payload = hub_proxy.delete_client(slug)
    if code == 204:
        return
    raise HTTPException(status_code=code if code >= 400 else 502, detail=payload.get("error") or "hub_error")


def _finops_by_slug(db: Session, *, hours: int, slug: str | None = None) -> list[dict]:
    from datetime import timedelta

    from sqlalchemy import func

    from app.models.invocation import Invocation

    since = datetime.utcnow() - timedelta(hours=max(1, min(hours, 24 * 90)))
    q = (
        db.query(
            Invocation.mcp_client_slug,
            func.count(Invocation.id),
            func.coalesce(func.sum(Invocation.input_tokens), 0),
            func.coalesce(func.sum(Invocation.output_tokens), 0),
            func.coalesce(func.sum(Invocation.estimated_cost), 0.0),
            func.coalesce(func.avg(Invocation.client_duration_ms), 0.0),
        )
        .filter(Invocation.source == "mcp_hub")
        .filter(Invocation.created_at >= since)
    )
    if slug:
        q = q.filter(Invocation.mcp_client_slug == slug)
    q = q.group_by(Invocation.mcp_client_slug)
    rows = []
    for s, n, tin, tout, cost, avg_ms in q.all():
        rows.append({
            "slug": s or "(unknown)",
            "invocations": int(n or 0),
            "input_tokens": int(tin or 0),
            "output_tokens": int(tout or 0),
            "estimated_cost": round(float(cost or 0), 6),
            "avg_duration_ms": round(float(avg_ms or 0), 1),
        })
    return rows


@ext_router.get("/analytics/summary")
def analytics_summary(
    hours: int = 24,
    slug: str | None = None,
    user: UserInfo = Depends(require_scopes("mcp:read")),
    db: Session = Depends(get_db),
) -> dict:
    _ = user
    code, payload = hub_proxy.analytics_summary(hours=hours, slug=slug)
    if code >= 400:
        raise HTTPException(status_code=code, detail=payload.get("error") or payload.get("detail") or "hub_error")
    finops = _finops_by_slug(db, hours=hours, slug=slug)
    by = {r["slug"]: r for r in finops}
    for c in payload.get("clients") or []:
        f = by.get(c.get("slug") or "")
        if f:
            c["finops"] = f
    payload["finops"] = {
        "invocations": sum(r["invocations"] for r in finops),
        "input_tokens": sum(r["input_tokens"] for r in finops),
        "output_tokens": sum(r["output_tokens"] for r in finops),
        "estimated_cost": round(sum(r["estimated_cost"] for r in finops), 6),
        "by_client": finops,
    }
    return payload


@ext_router.get("/analytics/tools")
def analytics_tools(
    hours: int = 24,
    slug: str | None = None,
    user: UserInfo = Depends(require_scopes("mcp:read")),
) -> dict:
    _ = user
    code, payload = hub_proxy.analytics_tools(hours=hours, slug=slug)
    if code >= 400:
        raise HTTPException(status_code=code, detail=payload.get("error") or payload.get("detail") or "hub_error")
    return payload


@ext_router.get("/analytics/errors")
def analytics_errors(
    hours: int = 24,
    slug: str | None = None,
    limit: int = 100,
    user: UserInfo = Depends(require_scopes("mcp:read")),
) -> dict:
    _ = user
    code, payload = hub_proxy.analytics_errors(hours=hours, slug=slug, limit=limit)
    if code >= 400:
        raise HTTPException(status_code=code, detail=payload.get("error") or payload.get("detail") or "hub_error")
    return payload
