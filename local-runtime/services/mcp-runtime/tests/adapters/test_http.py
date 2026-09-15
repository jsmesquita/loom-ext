import json
import os
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mcp_runtime.adapters.inbound.http_app as http_app
from mcp_runtime.adapters.inbound.http_app import RuntimeHandler
from mcp_runtime.adapters.outbound.process_supervisor import SUPERVISOR
from mcp_runtime.adapters.outbound.single_template import (
    SINGLE_SERVER_ID,
    configured_template_id,
    template_params_from_env,
)


class TestSingleTemplateEnv(unittest.TestCase):
    def tearDown(self) -> None:
        for key in ("TEMPLATE", "MCP_TEMPLATE", "MCP_TEMPLATE_PARAMS"):
            os.environ.pop(key, None)

    def test_template_prefers_TEMPLATE(self) -> None:
        os.environ["TEMPLATE"] = "azure-devops"
        os.environ["MCP_TEMPLATE"] = "grafana"
        self.assertEqual(configured_template_id(), "azure-devops")

    def test_params_json(self) -> None:
        os.environ["MCP_TEMPLATE_PARAMS"] = '{"organization":"acme"}'
        self.assertEqual(template_params_from_env(), {"organization": "acme"})


class TestRuntimeHttp(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["MCP_RUNTIME_TOKEN"] = "test-runtime-token"
        http_app._SINGLE = None
        SUPERVISOR.register(SINGLE_SERVER_ID, "test-echo", {}, [])
        SUPERVISOR.start(SINGLE_SERVER_ID)
        http_app._SINGLE = {"template_id": "test-echo", "server_id": SINGLE_SERVER_ID}
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), RuntimeHandler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        http_app._SINGLE = None
        try:
            SUPERVISOR.stop_all()
        except Exception:
            pass
        self.server.shutdown()
        self.server.server_close()

    def _url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def _json(self, method: str, path: str, body: dict | None = None, token: str | None = "test-runtime-token") -> tuple[int, dict]:
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        req = Request(self._url(path), data=data, headers=headers, method=method)
        try:
            with urlopen(req) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def test_health_is_public(self) -> None:
        status, payload = self._json("GET", "/health", token=None)
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["mode"], "single_template")

    def test_register_api_removed(self) -> None:
        status, payload = self._json(
            "POST",
            "/runtime/servers/register",
            {"server_id": 1, "template_id": "test-echo", "params": {}},
        )
        self.assertEqual(status, 404)

    def test_mcp_echo(self) -> None:
        status, payload = self._json(
            "POST",
            "/mcp",
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "echo", "arguments": {"text": "ping"}}},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["result"]["content"][0]["text"], "ping")

    def test_mcp_without_bearer(self) -> None:
        """Default: lateral trust — no token required."""
        status, payload = self._json(
            "POST",
            "/mcp",
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "echo", "arguments": {"text": "open"}}},
            token=None,
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["result"]["content"][0]["text"], "open")

    def test_mcp_require_auth_opt_in(self) -> None:
        os.environ["MCP_RUNTIME_REQUIRE_AUTH"] = "1"
        try:
            status, payload = self._json(
                "POST",
                "/mcp",
                {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                token=None,
            )
            self.assertEqual(status, 401)
            self.assertEqual(payload["error"]["code"], "runtime_auth")
            status_ok, _ = self._json(
                "POST",
                "/mcp",
                {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                token="test-runtime-token",
            )
            self.assertEqual(status_ok, 200)
        finally:
            os.environ.pop("MCP_RUNTIME_REQUIRE_AUTH", None)

    def test_legacy_s_path_gone(self) -> None:
        status, _ = self._json(
            "POST",
            "/s/1/mcp",
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
