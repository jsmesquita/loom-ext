"""Match Loom approval policies against MCP tool names (loop_hook)."""
from __future__ import annotations

import fnmatch
import logging
from typing import Any

logger = logging.getLogger("agent_runtime")


def find_loop_hook_policy(tool_name: str, policies: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the first enabled loop_hook policy whose globs match tool_name."""
    for policy in policies or []:
        if not isinstance(policy, dict):
            continue
        if not policy.get("enabled", True):
            continue
        if policy.get("policy_type") not in ("loop_hook", None):
            continue
        rules = policy.get("tool_match_rules") or []
        if not isinstance(rules, list):
            continue
        if not rules:
            # Empty rules = match all (same as ADK/Strands matcher).
            return policy
        for pattern in rules:
            if isinstance(pattern, str) and fnmatch.fnmatch(tool_name, pattern):
                return policy
    return None


def policy_matches_any(names: list[str], policies: list[dict[str, Any]]) -> dict[str, Any] | None:
    for name in names:
        if not name:
            continue
        hit = find_loop_hook_policy(name, policies)
        if hit is not None:
            logger.info("approval policy %r matched tool %r", hit.get("name"), name)
            return hit
    return None
