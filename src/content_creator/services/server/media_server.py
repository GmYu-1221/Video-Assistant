from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import mimetypes
from pathlib import Path
import re
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
            def _serve(self, *, send_body: bool) -> None:
                relative = unquote(urlparse(self.path).path).lstrip("/")
                if not relative.startswith(("materials/", "audio/", "background/")):
                    self.send_error(403); return
                try:
                    target = safe_child(root, relative)
                    if not target.is_file():
                        raise ValueError("missing file")
                    size = target.stat().st_size
                except (ValueError, OSError):
                    self.send_error(404); return
                start, end = 0, max(0, size - 1)
                range_header = self.headers.get("Range", "")
                if range_header:
                    match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
                    if not match:
                        self.send_error(416); return
                    if match.group(1):
                        start = int(match.group(1))
                        end = min(end, int(match.group(2))) if match.group(2) else end
                    elif match.group(2):
                        length = min(size, int(match.group(2)))
                        start = size - length
                    if start >= size or end < start:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{size}")
                        self.end_headers()
                        return
                length = end - start + 1
                self.send_response(206 if range_header else 200)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(length))
                self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
                if range_header:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.end_headers()
                if send_body:
                    with target.open("rb") as source:
                        source.seek(start)
                        remaining = length
                        while remaining:
                            chunk = source.read(min(1024 * 1024, remaining))
                            if not chunk:
                                break
                            try:
                                self.wfile.write(chunk)
                            except (BrokenPipeError, ConnectionResetError):
                                # Chromium cancels superseded Range requests while
                                # seeking media. The next request resumes playback.
                                break
                            remaining -= len(chunk)

            def do_GET(self):
                self._serve(send_body=True)

            def do_HEAD(self):
                self._serve(send_body=False)

            def do_OPTIONS(self):
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Range")
                self.end_headers()

            def log_message(self, *_args):
                return
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = Thread(target=self._server.serve_forever, daemon=True); self._thread.start()
        return f"http://127.0.0.1:{self._server.server_port}"

    def close(self) -> None:
        if self._server:
            self._server.shutdown(); self._server.server_close(); self._server = None
        self._thread = None
