"""Admin RBAC for Hub ops API (browser → Hub, no Loom BFF proxy).

Mirrors the mcp:read / mcp:write subset of Loom GROUP_SCOPES so the plugin
can call Hub /v1/* with the same SPA JWT used for Loom APIs.
"""
from __future__ import annotations

# Keep in sync with backend/app/dependencies/auth.py GROUP_SCOPES for mcp:*.
_GROUP_MCP_SCOPES: dict[str, frozenset[str]] = {
    "g-admins-super": frozenset({"mcp:read", "mcp:write"}),
    "g-admins-demo": frozenset({"mcp:read", "mcp:write"}),
    "g-admins-mcp": frozenset({"mcp:read", "mcp:write"}),
    "g-admins-registry": frozenset({"mcp:read"}),
    "g-users-demo": frozenset({"mcp:read"}),
    "g-users-test": frozenset({"mcp:read"}),
    "g-users-strategics": frozenset({"mcp:read"}),
}


def scopes_for_groups(groups: list[str]) -> set[str]:
    out: set[str] = set()
    for g in groups or []:
        out |= _GROUP_MCP_SCOPES.get(str(g), frozenset())
    return out


def has_scope(groups: list[str], scope: str) -> bool:
    scopes = scopes_for_groups(groups)
    if scope in scopes:
        return True
    # write implies read
    if scope == "mcp:read" and "mcp:write" in scopes:
        return True
    return False
