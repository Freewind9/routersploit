"""Minimal conftest providing the `target` fixture via http.server.

Replaces threat9_test_bed which is not pip-installable on Windows.
The fixture exposes `host`, `port`, `get_route_mock()`, and `httpd`.
"""
import http.server
import json as _json
import threading
from unittest import mock

import pytest


class _RouteHandler(http.server.BaseHTTPRequestHandler):
    routes = {}  # {"POST /path": mock.Mock}

    def _handle(self):
        key = "{} {}".format(self.command, self.path.split("?")[0])
        m = self.routes.get(key)
        if m is not None:
            body = m.return_value if isinstance(m.return_value, str) else ""
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body.encode())
        else:
            self.send_response(404)
            self.end_headers()

    do_GET = do_POST = do_PUT = do_DELETE = _handle

    def log_message(self, *args):
        pass


class _Target:
    def __init__(self, host, port, httpd):
        self.host = host
        self.port = port
        self.httpd = httpd

    def get_route_mock(self, path, methods=None):
        key = "{} {}".format((methods or ["GET"])[0], path)
        m = mock.Mock()
        _RouteHandler.routes[key] = m
        return m


@pytest.fixture
def target():
    server = http.server.HTTPServer(("127.0.0.1", 0), _RouteHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield _Target("127.0.0.1", server.server_port, server)
    server.shutdown()
    _RouteHandler.routes.clear()
