"""Local Studio contract fixture; no BandLab branding, network or authentication."""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator


@contextmanager
def start_fixture() -> Iterator[str]:
    """Serve an isolated in-memory project store on an OS-assigned loopback port."""
    projects: dict[str, dict] = {}
    page = Path(__file__).with_suffix(".html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            if self.path.split("?")[0] == "/api/project":
                body, content_type = json.dumps(projects).encode(), "application/json"
            else:
                body, content_type = page, "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            if self.path != "/api/project":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length < 1024 * 1024:
                self.send_error(413)
                return
            try:
                project = json.loads(self.rfile.read(length))
                projects[project["title"]] = project
            except (ValueError, KeyError):
                self.send_error(400)
                return
            self.send_response(204)
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/studio"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
