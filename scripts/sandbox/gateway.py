"""Minimal HTTP allowlist gateway for the CodeAct sandbox.

The sandbox reaches only this process on an internal Docker network. This gateway
selects the Java or Router host service from its internal DNS alias and rejects
all methods and paths not required by Phase 1 tools.
"""

from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ALLOWED = {
    "router-proxy": {("GET", "/health/ready"), ("POST", "/v1/chat/completions")},
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
            self.send_error(403, "sandbox gateway policy denied request")
            return
        port = 8000 if alias == "router-proxy" else 8080
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        connection = HTTPConnection("host.docker.internal", port, timeout=30)
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in {"host", "connection"}
        }
        try:
            connection.request(self.command, self.path, body=body, headers=headers)
            upstream = connection.getresponse()
            data = upstream.read()
            self.send_response(upstream.status)
            self.send_header("Content-Type", upstream.getheader("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        finally:
            connection.close()

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
