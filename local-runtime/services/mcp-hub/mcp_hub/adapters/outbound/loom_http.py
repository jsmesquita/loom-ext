"""Loom gateway: user JWT to native APIs + direct MCP upstream (ADR 0015)."""
from __future__ import annotations

import os
from typing import Any

from mcp_hub.adapters.outbound import agents_native, catalog, mcp_upstream


def service_token() -> str:
    """Optional: still used for Hub admin routes called by the Loom BFF plugin."""
    return os.environ.get("MCP_HUB_SERVICE_TOKEN", "").strip()


def _token(kwargs: dict[str, Any]) -> str:
    return str(kwargs.get("access_token") or "").strip()


class LoomHttpGateway:
    """Outbound adapter implementing ``LoomGateway`` (ADR 0015)."""

    def service_token(self) -> str:
        return service_token()

    def materialize_allowlist(
        self,
        *,
        subject: str,
        groups: list[str],
        connection_id: str,
        mcp_client_slug: str,
        client_status: str,
        grants: list[dict[str, Any]],
        access_token: str = "",
    ) -> tuple[int, dict[str, Any]]:
        _ = groups
        return catalog.materialize_entries_from_grants(
            access_token=access_token,
            subject=subject,
            connection_id=connection_id,
            mcp_client_slug=mcp_client_slug,
            client_status=client_status,
            grants=grants,
        )

    def tools_call(
        self,
        *,
        subject: str,
        groups: list[str],
        tool_name: str,
        arguments: dict[str, Any],
        server_id: int,
        original_tool_name: str,
        endpoint_url: str = "",
        access_token: str = "",
    ) -> tuple[int, dict[str, Any]]:
        _ = subject, groups, tool_name, server_id, access_token
        if not endpoint_url:
            return 400, {"success": False, "error": "missing_endpoint_url"}
        return mcp_upstream.call_mcp_tool(
            endpoint_url=endpoint_url,
            tool_name=original_tool_name,
            arguments=arguments or {},
        )

    def materialize_agents(
        self, *, subject: str, groups: list[str], access_token: str = ""
    ) -> tuple[int, dict[str, Any]]:
        _ = subject, groups
        return agents_native.materialize_agents(access_token=access_token)

    def agents_invoke(
        self,
        *,
        subject: str,
        groups: list[str],
        agent_id: int,
        prompt: str,
        session_id: str | None = None,
        mode: str = "async",
        timeout_s: int = 120,
        hub_server_ids: list[int] | None = None,
        hub_tool_allowlists: dict[str, list[str]] | None = None,
        mcp_client_slug: str | None = None,
        hub_session_id: str | None = None,
        wait_mode: str | None = None,
        access_token: str = "",
    ) -> tuple[int, dict[str, Any]]:
        _ = subject, groups, hub_tool_allowlists, mcp_client_slug, hub_session_id, wait_mode
        return agents_native.agents_invoke(
            access_token=access_token,
            agent_id=agent_id,
            prompt=prompt,
            session_id=session_id,
            mode=mode,
            timeout_s=timeout_s,
            hub_server_ids=hub_server_ids,
        )

    def agents_run(
        self, *, subject: str, groups: list[str], session_id: str, access_token: str = ""
    ) -> tuple[int, dict[str, Any]]:
        _ = subject, groups, access_token
        return agents_native.agents_run(session_id=session_id)
