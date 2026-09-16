"""Unit tests for Hub admin RBAC scopes."""
from __future__ import annotations

import unittest

from mcp_hub.domain.admin_rbac import has_scope, scopes_for_groups


class TestAdminRbac(unittest.TestCase):
    def test_super_write(self) -> None:
        self.assertIn("mcp:write", scopes_for_groups(["g-admins-super"]))
        self.assertTrue(has_scope(["g-admins-super"], "mcp:write"))
        self.assertTrue(has_scope(["g-admins-super"], "mcp:read"))

    def test_user_read_only(self) -> None:
        self.assertEqual(scopes_for_groups(["g-users-demo"]), {"mcp:read"})
        self.assertTrue(has_scope(["g-users-demo"], "mcp:read"))
        self.assertFalse(has_scope(["g-users-demo"], "mcp:write"))

    def test_unknown_group(self) -> None:
        self.assertEqual(scopes_for_groups(["t-admin"]), set())
        self.assertFalse(has_scope(["t-admin"], "mcp:read"))


if __name__ == "__main__":
    unittest.main()
