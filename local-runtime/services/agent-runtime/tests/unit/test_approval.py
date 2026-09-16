"""Unit tests for loop_hook approval matching."""
from __future__ import annotations

import unittest

from agent_runtime.domain.approval import find_loop_hook_policy, policy_matches_any


class ApprovalMatchTests(unittest.TestCase):
    def test_matches_exact_and_glob(self) -> None:
        policies = [{
            "name": "gate",
            "policy_type": "loop_hook",
            "approval_mode": "require_approval",
            "enabled": True,
            "tool_match_rules": ["echo", "book_*"],
        }]
        self.assertEqual(find_loop_hook_policy("echo", policies)["name"], "gate")
        self.assertEqual(find_loop_hook_policy("book_hotel", policies)["name"], "gate")
        self.assertIsNone(find_loop_hook_policy("weather", policies))

    def test_skips_non_loop_hook(self) -> None:
        policies = [{
            "name": "ctx",
            "policy_type": "tool_context",
            "enabled": True,
            "tool_match_rules": ["echo"],
        }]
        self.assertIsNone(find_loop_hook_policy("echo", policies))

    def test_matches_any_candidates(self) -> None:
        policies = [{
            "name": "gate",
            "policy_type": "loop_hook",
            "enabled": True,
            "tool_match_rules": ["echo"],
        }]
        hit = policy_matches_any(["srv__echo", "echo"], policies)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["name"], "gate")


if __name__ == "__main__":
    unittest.main()
