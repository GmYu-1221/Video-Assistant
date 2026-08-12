from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import unquote, urlparse
from content_creator.security.files import safe_child


class MediaServer:
    def __init__(self, project_dir: str | Path):
        self.project_dir = Path(project_dir).resolve()
        self._server: ThreadingHTTPServer | None = None
        self._thread: Thread | None = None

    def start(self) -> str:
        root = self.project_dir
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                relative = unquote(urlparse(self.path).path).lstrip("/")
                if not (relative.startswith("materials/") or relative.startswith("audio/")):
                    self.send_error(403); return
                try:
                    target = safe_child(root, relative)
                    if not target.is_file():
                        raise ValueError("missing file")
                    data = target.read_bytes()
                except (ValueError, OSError):
                    self.send_error(404); return
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Content-Type", "application/octet-stream")
                self.end_headers(); self.wfile.write(data)
            def log_message(self, *_args):
                return
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = Thread(target=self._server.serve_forever, daemon=True); self._thread.start()
        return f"http://127.0.0.1:{self._server.server_port}"

    def close(self) -> None:
        if self._server:
            self._server.shutdown(); self._server.server_close(); self._server = None
        self._thread = None
