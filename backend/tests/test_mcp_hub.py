"""Tests for MCP Hub BFF after ADR 0015 phase 5 (data-plane removed from Core)."""
import os
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db import Base, get_db
from app.dependencies.auth import UserInfo, get_current_user


def _admin() -> UserInfo:
    return UserInfo(
        sub="user-1",
        username="admin",
        groups=["t-admin", "g-admins-super"],
        scopes={"mcp:read", "mcp:write", "invoke", "admin:write", "agent:read"},
        idp_type="keycloak",
    )


class TestMcpHub(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=cls.engine)
        cls.TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)

    def setUp(self):
        self.session = self.TestingSessionLocal()

        def override_get_db():
            try:
                yield self.session
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = _admin
        os.environ["MCP_HUB_SERVICE_TOKEN"] = "test-hub-token"
        os.environ["MCP_HUB_PUBLIC_URL"] = "http://127.0.0.1:8790/mcp"
        self.client = TestClient(app)

    def tearDown(self):
        self.session.rollback()
        self.session.close()
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        app.dependency_overrides.clear()

    def test_hub_info_oauth(self):
        resp = self.client.get("/api/mcp/hub/info")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["auth"], "oauth")
        self.assertTrue(body["mcp_hub_url"].endswith("/mcp"))
        self.assertEqual(body["contract_version"], "2026-09-hub-1")

    def test_data_plane_routes_absent(self):
        """ADR 0015 phase 5: Hub data-plane no longer on Loom Core."""
        token = {"Authorization": "Bearer test-hub-token"}
        self.assertEqual(
            self.client.post(
                "/api/mcp/hub/materialize-allowlist",
                headers=token,
                json={
                    "subject": "u1",
                    "groups": [],
                    "mcp_client_slug": "cursor",
                    "client_status": "enabled",
                    "grants": [],
                },
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                "/api/mcp/hub/tools/call",
                headers=token,
                json={"subject": "u1", "groups": [], "tool_name": "x", "arguments": {}},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                "/api/mcp/hub/materialize-agents",
                headers=token,
                json={"subject": "u1", "groups": []},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                "/api/mcp/hub/agents/invoke",
                headers=token,
                json={"subject": "u1", "groups": [], "agent_id": 1, "prompt": "hi"},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                "/api/mcp/hub/agents/runs/sess-1",
                headers=token,
                json={"subject": "u1", "groups": []},
            ).status_code,
            404,
        )

    def test_mint_routes_absent(self):
        self.assertEqual(self.client.post("/api/mcp/hub/sessions", json={}).status_code, 404)
        self.assertEqual(self.client.delete("/api/mcp/hub/sessions/any").status_code, 404)


if __name__ == "__main__":
    unittest.main()
