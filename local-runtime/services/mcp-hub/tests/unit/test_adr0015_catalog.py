"""Unit tests for ADR 0015 catalog / upstream / dual-aud token helpers."""
from __future__ import annotations

import json
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any
from urllib.request import Request, urlopen


class _CatalogHandler(BaseHTTPRequestHandler):
    server_payload: dict[str, Any] = {}
    tools_payload: list[dict[str, Any]] = []

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        if self.path.endswith("/tools"):
            body = json.dumps(self.tools_payload).encode()
        else:
            body = json.dumps(self.server_payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _McpHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length)
        req = json.loads(raw.decode() or "{}")
        params = req.get("params") or {}
        result = {
            "content": [{"type": "text", "text": f"echo:{params.get('arguments', {}).get('x', '')}"}],
        }
        body = json.dumps({"jsonrpc": "2.0", "id": req.get("id"), "result": result}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class TestDualAudToken(unittest.TestCase):
    def test_dual_aud_passthrough(self) -> None:
        from mcp_hub.adapters.outbound.token_exchange import loom_api_token

        self.assertEqual(loom_api_token("abc.jwt.token"), "abc.jwt.token")


class TestCatalogMaterialize(unittest.TestCase):
    def setUp(self) -> None:
        _CatalogHandler.server_payload = {
            "id": 1,
            "name": "Echo",
            "endpoint_url": "http://mcp-echo:8787/mcp",
            "transport_type": "streamable_http",
            "status": "active",
        }
        _CatalogHandler.tools_payload = [
            {"tool_name": "ping", "description": "p", "input_schema": {"type": "object"}},
            {"tool_name": "other", "description": "o", "input_schema": {"type": "object"}},
        ]
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _CatalogHandler)
        self.port = self.httpd.server_address[1]
        self.thread = Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    def test_intersect_selected_tools(self) -> None:
        import mcp_hub.adapters.outbound.loom_user_http as loom_http
        from mcp_hub.adapters.outbound.catalog import materialize_entries_from_grants

        original = loom_http.loom_base
        loom_http.loom_base = lambda: f"http://127.0.0.1:{self.port}"  # type: ignore[method-assign]
        try:
            code, payload = materialize_entries_from_grants(
                access_token="tok",
                subject="u1",
                connection_id="oauth:u1",
                mcp_client_slug="cursor",
                client_status="enabled",
                grants=[{
                    "group": "g-users-demo",
                    "server_id": 1,
                    "access_level": "selected_tools",
                    "tool_names": ["ping"],
                }],
            )
        finally:
            loom_http.loom_base = original  # type: ignore[method-assign]
        self.assertEqual(code, 200)
        self.assertEqual(len(payload["entries"]), 1)
        names = [t["name"] for t in payload["entries"][0]["tools"]]
        self.assertEqual(names, ["ping"])


class TestMcpUpstream(unittest.TestCase):
    def setUp(self) -> None:
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _McpHandler)
        self.port = self.httpd.server_address[1]
        self.thread = Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    def test_tools_call(self) -> None:
        from mcp_hub.adapters.outbound.mcp_upstream import call_mcp_tool

        status, result = call_mcp_tool(
            endpoint_url=f"http://127.0.0.1:{self.port}/mcp",
            tool_name="echo",
            arguments={"x": "hi"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(result.get("success"))
        text = result["result"]["content"][0]["text"]
        self.assertEqual(text, "echo:hi")


if __name__ == "__main__":
    unittest.main()
