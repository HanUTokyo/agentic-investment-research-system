"""Minimal HTTP allowlist gateway for the CodeAct sandbox.

The sandbox reaches only this process on an internal Docker network. This gateway
selects the Java or Router host service from its internal DNS alias and rejects
all methods and paths not required by Phase 1 tools.
"""

import json
import os
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ALLOWED = {
    "router-proxy": {("GET", "/health/ready"), ("POST", "/v1/chat/completions")},
    "controller-proxy": {("POST", "/v1/chat/completions")},
    "stock-proxy": {
        ("GET", "/v3/api-docs"),
        ("GET", "/api/portfolio/export/v2"),
        ("GET", "/api/portfolio/history/fundamentals"),
        ("GET", "/api/portfolio/history/capital-allocation"),
    },
}


class Gateway(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self._forward()

    def do_POST(self):
        self._forward()

    def _forward(self):
        alias = self.headers.get("Host", "").split(":", 1)[0]
        path = self.path.split("?", 1)[0]
        if not self._allowed(alias, self.command, path):
            self._log_request(alias, path, None, 403)
            self.send_error(403, "sandbox gateway policy denied request")
            return
        if alias == "router-proxy":
            host, port = os.environ.get("SANDBOX_ROUTER_HOST", "host.docker.internal"), 8000
        elif alias == "controller-proxy":
            host, port = os.environ.get("SANDBOX_CONTROLLER_HOST", "host.docker.internal"), 11434
        else:
            host, port = os.environ.get("SANDBOX_STOCK_HOST", "host.docker.internal"), 8080
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        # R1's local reasoning can legitimately take longer than the agent's
        # default request budget.  This gateway must not sever an otherwise
        # healthy serial request first.
        connection = HTTPConnection(
            host,
            port,
            timeout=float(os.environ.get("SANDBOX_UPSTREAM_TIMEOUT_SECONDS", "315")),
        )
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in {"host", "connection"}
        }
        try:
            connection.request(self.command, self.path, body=body, headers=headers)
            upstream = connection.getresponse()
            data = upstream.read()
            self._log_request(alias, path, body, upstream.status)
            self.send_response(upstream.status)
            self.send_header("Content-Type", upstream.getheader("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        finally:
            connection.close()

    def _log_request(self, alias: str, path: str, body: bytes | None, status: int) -> None:
        """Emit structural diagnostics only; request content is never logged."""
        summary: dict[str, object] = {
            "event": "sandbox_gateway_request",
            "alias": alias,
            "method": self.command,
            "path": path,
            "status": status,
            "content_length": len(body or b""),
        }
        if body:
            try:
                payload = json.loads(body)
            except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
                summary["json"] = "invalid_or_non_json"
            else:
                if isinstance(payload, dict):
                    summary["json_keys"] = sorted(payload.keys())
                    if payload.get("route_hint") in {"chat", "reason", "code"}:
                        summary["route_hint"] = payload["route_hint"]
                    tools = payload.get("tools")
                    if isinstance(tools, list):
                        summary["tool_names"] = sorted(
                            str(item.get("function", {}).get("name", "unknown"))
                            for item in tools
                            if isinstance(item, dict)
                        )
                    messages = payload.get("messages")
                    if isinstance(messages, list):
                        summary["message_roles"] = [
                            str(item.get("role", "unknown"))
                            for item in messages
                            if isinstance(item, dict)
                        ]
        print(json.dumps(summary, sort_keys=True), flush=True)

    @staticmethod
    def _allowed(alias: str, method: str, path: str) -> bool:
        if alias == "stock-proxy" and path.startswith("/api/valuations/"):
            return (method == "GET" and path.count("/") == 3) or (
                method == "POST" and path.endswith("/evaluate") and path.count("/") == 4
            )
        for allowed_method, prefix in ALLOWED.get(alias, set()):
            if method == allowed_method and (path == prefix or path.startswith(prefix)):
                return True
        return False

    def log_message(self, *_):
        return


ThreadingHTTPServer(("0.0.0.0", 8080), Gateway).serve_forever()  # noqa: S104
