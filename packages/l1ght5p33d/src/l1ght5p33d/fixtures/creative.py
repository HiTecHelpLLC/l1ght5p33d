"""Harmless local poster fixture with semantic controls and durable readback."""

from __future__ import annotations

import json
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Iterator

HTML = b"""<!doctype html><html lang="en"><title>L1ght5p33d Poster Studio</title>
<style>body{font:18px system-ui;background:#f5f2ec;margin:50px;max-width:900px}label{display:block;margin:20px 0}
input,select,button{font:inherit;padding:12px}article{padding:40px;background:#194849;color:white;font-size:40px}</style>
<h1>Poster Studio</h1><label>Poster title <input id="poster_title" aria-label="Poster title"></label>
<label>Palette <select id="palette" aria-label="Palette"><option>Ocean</option><option>Sunset</option></select></label>
<button id="save">Save poster</button><output id="saved" role="status">Unsaved</output><article id="preview">Your poster</article>
<script>save.onclick=async()=>{saved.value='Saving'; const r=await fetch('/save',{method:'POST',
headers:{'Content-Type':'application/json'},body:JSON.stringify({poster_title:poster_title.value,palette:palette.value})});
saved.value=r.ok?'Saved':'Save failed';preview.textContent=poster_title.value;};</script></html>"""


@contextmanager
def serve_creative_fixture(*, port: int = 0) -> Iterator[str]:
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("Fixture port must be an integer from 0 to 65535")
    state: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            pass

        def do_GET(self) -> None:
            body = json.dumps(state).encode() if self.path == "/state" else HTML
            self.send_response(200)
            self.send_header(
                "Content-Type",
                "application/json" if self.path == "/state" else "text/html",
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            size = int(self.headers.get("Content-Length", "0"))
            if self.path != "/save" or size > 4096:
                self.send_error(400)
                return
            state.update(json.loads(self.rfile.read(size)))
            self.send_response(204)
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
