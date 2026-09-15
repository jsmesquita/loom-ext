"""MCP Hub control-plane helpers kept in Core for ops BFF (ADR 0015).

Data-plane materialize / tools/call / agents moved to the Hub sidecar.
"""
from __future__ import annotations

import os

CONTRACT_VERSION = "2026-09-hub-1"


def hub_public_url() -> str:
    return os.getenv("MCP_HUB_PUBLIC_URL", "http://127.0.0.1:8790/mcp").rstrip("/")
