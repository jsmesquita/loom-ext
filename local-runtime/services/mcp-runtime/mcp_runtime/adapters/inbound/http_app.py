"""Internal HTTP facade. TEMPLATE= mode; lateral trust (Docker / loopback).

No service bearer on ``/mcp`` by default — Loom registers hosts as ``auth=none``
and stays Core-intact. Opt-in: ``MCP_RUNTIME_REQUIRE_AUTH=1`` + ``MCP_RUNTIME_TOKEN``.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, ClassVar
from urllib.parse import urlparse

from mcp_runtime.adapters.outbound.single_template import (
    SINGLE_SERVER_ID,
    boot_single_template,
    configured_template_id,
)
from mcp_runtime.adapters.outbound.yaml_templates import public_templates
from mcp_runtime.application.ports import ProcessSupervisor
from mcp_runtime.application.wiring import default_supervisor
from mcp_runtime.domain.errors import SecretError, TemplateError

logger = logging.getLogger("mcp_runtime")

_SINGLE: dict[str, Any] | None = None


def runtime_token() -> str:
    return os.environ.get("MCP_RUNTIME_TOKEN", "").strip()


def _require_auth() -> bool:
    return os.environ.get("MCP_RUNTIME_REQUIRE_AUTH", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _authorized(handler: BaseHTTPRequestHandler) -> bool:
    if not _require_auth():
        return True
    expected = runtime_token()
    if not expected:
        return False
    header = handler.headers.get("Authorization", "")
    return header == f"Bearer {expected}"


def _allowed_tools(handler: BaseHTTPRequestHandler) -> set[str] | None:
    raw = handler.headers.get("X-Loom-Allowed-Tools", "").strip()
    if not raw or raw == "*":
        return None
    return {part.strip() for part in raw.split(",") if part.strip()}


def _json(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    raw = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


class RuntimeHandler(BaseHTTPRequestHandler):
    supervisor: ClassVar[ProcessSupervisor]

    def log_message(self, fmt: str, *args: Any) -> None:
        logger.info(fmt, *args)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            payload: dict[str, Any] = {"status": "ok", "mode": "single_template"}
            if _SINGLE:
                payload["template_id"] = _SINGLE.get("template_id")
            _json(self, 200, payload)
            return
        if not _authorized(self):
            _json(self, 401, {"error": {"message": "unauthorized", "code": "runtime_auth"}})
            return
        if parsed.path == "/runtime/templates":
            _json(self, 200, {"templates": public_templates()})
            return
        if parsed.path == "/runtime/servers/1/health":
            try:
                _json(self, 200, self.supervisor.health(SINGLE_SERVER_ID))
            except KeyError:
                _json(self, 404, {"error": {"message": "unknown_server"}})
            return
        _json(self, 404, {"error": {"message": "not_found"}})

    def do_POST(self) -> None:  # noqa: N802
        if not _authorized(self):
            _json(self, 401, {"error": {"message": "unauthorized", "code": "runtime_auth"}})
            return
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            _json(self, 400, {"error": {"message": "invalid_json"}})
            return
        path = urlparse(self.path).path
        try:
            if path != "/mcp":
                _json(self, 404, {"error": {"message": "not_found"}})
                return
            if _SINGLE is None:
                _json(self, 503, {"error": {"message": "template_not_ready", "code": "not_ready"}})
                return
            self._mcp(SINGLE_SERVER_ID, body)
        except TemplateError as exc:
            _json(self, 400, {"error": {"message": str(exc), "code": "template_error"}})
        except SecretError as exc:
            _json(self, 400, {"error": {"message": str(exc), "code": "secret_unresolved"}})
        except KeyError:
            _json(self, 404, {"error": {"message": "unknown_server"}})
        except Exception as exc:
            logger.exception("runtime error")
            message = str(exc)
            if "environment variable" in message or len(message) > 80:
                message = "runtime_error"
            _json(self, 500, {"error": {"message": message, "code": "runtime_error"}})

    def _mcp(self, server_id: int, body: dict[str, Any]) -> None:
        method = body.get("method")
        params = body.get("params")
        allowed = _allowed_tools(self)
        if method == "tools/list" and allowed is not None:
            result = self.supervisor.call(server_id, "tools/list", params)
            tools = (result.get("result") or {}).get("tools") or []
            filtered = [tool for tool in tools if tool.get("name") in allowed]
            result = {**result, "result": {**(result.get("result") or {}), "tools": filtered}}
            _json(self, 200, result)
            return
        if method == "tools/call" and allowed is not None:
            name = (params or {}).get("name")
            if name not in allowed:
                _json(self, 403, {
                    "jsonrpc": "2.0",
                    "id": body.get("id"),
                    "error": {"code": 403, "message": "tool_denied"},
                })
                return
        result = self.supervisor.call(server_id, str(method), params)
        _json(self, 200, result)


def _wire_defaults() -> None:
    RuntimeHandler.supervisor = default_supervisor()


_wire_defaults()


def serve(
    host: str | None = None,
    port: int | None = None,
    *,
    supervisor: ProcessSupervisor | None = None,
) -> None:
    global _SINGLE
    RuntimeHandler.supervisor = supervisor or default_supervisor()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    tid = configured_template_id()
    if not tid:
        logger.error("TEMPLATE / MCP_TEMPLATE is required (one MCP per container)")
        sys.exit(1)
    _SINGLE = boot_single_template(RuntimeHandler.supervisor, tid)
    logger.info(
        "mode=single_template template=%s path=/mcp require_auth=%s",
        tid,
        _require_auth(),
    )

    bind_host = host or os.environ.get("MCP_RUNTIME_HOST", "127.0.0.1")
    bind_port = port or int(os.environ.get("MCP_RUNTIME_PORT", "8787"))
    server = ThreadingHTTPServer((bind_host, bind_port), RuntimeHandler)
    logger.info("mcp-runtime listening on %s:%s", bind_host, bind_port)
    try:
        server.serve_forever()
    finally:
        RuntimeHandler.supervisor.stop_all()
        server.server_close()
