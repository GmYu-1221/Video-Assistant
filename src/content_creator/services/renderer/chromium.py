"""Deterministic HTML frame capture piped directly into FFmpeg."""
from __future__ import annotations

import functools
import json
import subprocess
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

from content_creator.schemas import AnimationArtifact


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args) -> None:
        return


class ChromiumRenderer:
    def __init__(self, *, ready_timeout_ms: int = 30_000) -> None:
        self.ready_timeout_ms = ready_timeout_ms

    def render(
        self, artifact: AnimationArtifact, project_dir: str | Path,
        bgm_path: str | Path, output_path: str | Path, on_progress=None,
    ) -> Path:
        project = Path(project_dir).resolve()
        bgm = Path(bgm_path).resolve()
        output = Path(output_path).resolve()
        if not bgm.is_file():
            raise FileNotFoundError(f"Adapted BGM does not exist: {bgm}")
        output.parent.mkdir(parents=True, exist_ok=True)
        duration = artifact.duration_frames / artifact.fps
        command = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "image2pipe", "-vcodec", "png", "-framerate", str(artifact.fps), "-i", "pipe:0",
            "-i", str(bgm), "-map", "0:v:0", "-map", "1:a:0",
            "-t", f"{duration:.6f}", "-c:v", "libx264", "-preset", "medium",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output),
        ]
        ffmpeg = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if ffmpeg.stdin is None:
            raise RuntimeError("FFmpeg stdin pipe was not created")
        handler = functools.partial(_QuietHandler, directory=str(project))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}/"
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": artifact.width, "height": artifact.height}, device_scale_factor=1)

                def route_request(route) -> None:
                    if route.request.url.startswith(base_url):
                        route.continue_()
                    else:
                        route.abort("blockedbyclient")

                page.route("**/*", route_request)
                page.goto(base_url + "animation.html", wait_until="load")
                page.wait_for_function("window.__ANIMATION_READY__ === true", timeout=self.ready_timeout_ms)
                page.evaluate("""async () => {
                    await document.fonts.ready;
                    await Promise.all(Array.from(document.images).map(image => image.complete
                        ? Promise.resolve()
                        : new Promise((resolve, reject) => {
                            image.addEventListener('load', resolve, {once: true});
                            image.addEventListener('error', reject, {once: true});
                        })));
                    if (Array.from(document.images).some(image => image.naturalWidth === 0)) {
                        throw new Error('A local animation image failed to load');
                    }
                }""")
                meta = page.evaluate("window.__ANIMATION_META__")
                expected = {
                    "width": artifact.width, "height": artifact.height, "fps": artifact.fps,
                    "durationFrames": artifact.duration_frames,
                }
                if meta != expected:
                    raise RuntimeError(f"Animation runtime meta mismatch: {json.dumps(meta)}")
                for frame in range(artifact.duration_frames):
                    page.evaluate("frame => window.renderFrame(frame)", frame)
                    png = page.screenshot(type="png", animations="allow")
                    ffmpeg.stdin.write(png)
                    if on_progress and (frame == 0 or frame + 1 == artifact.duration_frames or (frame + 1) % max(1, artifact.fps) == 0):
                        on_progress(frame + 1, artifact.duration_frames)
                browser.close()
            ffmpeg.stdin.close()
            stderr = ffmpeg.stderr.read().decode("utf-8", "replace") if ffmpeg.stderr else ""
            code = ffmpeg.wait()
            if code:
                raise RuntimeError(f"FFmpeg failed ({code}): {stderr[-2000:]}")
        except Exception:
            try:
                if ffmpeg.stdin and not ffmpeg.stdin.closed:
                    ffmpeg.stdin.close()
            except (BrokenPipeError, OSError):
                pass
            ffmpeg.kill()
            ffmpeg.wait()
            output.unlink(missing_ok=True)
            raise
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        if not output.is_file() or output.stat().st_size == 0:
            raise RuntimeError("Renderer did not create final.mp4")
        return output
