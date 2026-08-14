"""Local single-input web application for URL video generation."""
from __future__ import annotations

import asyncio
import hmac
import json
import os
import secrets
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit, urlunsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from content_creator.services.renderer import render_project
from content_creator.services.article import BrowserImportRequired, MAX_HTML_BYTES
from content_creator.services.url_video import create_url_project


@dataclass
class Job:
    id: str
    url: str
    status: str = "queued"
    stage: str = "等待开始"
    error: str | None = None
    project_dir: str | None = None
    video_path: str | None = None
    browser_import_status: int | None = None
    browser_import_url: str | None = None
    events: list[dict[str, str]] = field(default_factory=list)

    def event(self, stage: str) -> None:
        self.stage = stage
        self.events.append({"status": self.status, "stage": stage})


class JobRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


class JobManager:
    def __init__(self, output_root: Path, repo_root: Path):
        self.output_root, self.repo_root = output_root, repo_root
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.import_token_path = self.output_root / ".browser-import-token"
        if self.import_token_path.is_file():
            self.import_token = self.import_token_path.read_text(encoding="utf-8").strip()
        else:
            self.import_token = secrets.token_urlsafe(32)
            self.import_token_path.write_text(self.import_token, encoding="utf-8")
            os.chmod(self.import_token_path, 0o600)
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="url-video")

    def submit(self, url: str, import_base_url: str = "http://127.0.0.1:8000") -> Job:
        job = Job(id=uuid.uuid4().hex, url=url)
        job.browser_import_url = self.browser_import_url(import_base_url)
        with self.lock:
            self.jobs[job.id] = job
        self.executor.submit(self._run, job)
        return job

    def get(self, job_id: str) -> Job:
        with self.lock:
            job = self.jobs.get(job_id)
        if not job:
            raise KeyError(job_id)
        return job

    def browser_import_url(self, import_base_url: str = "http://127.0.0.1:8000") -> str:
        action = f"{import_base_url.rstrip('/')}/api/browser-import"
        script = """javascript:(()=>{const f=document.createElement('form');f.method='POST';f.action=ACTION;f.target='_blank';for(const [k,v] of [['token',TOKEN],['source_url',location.href],['html',document.documentElement.outerHTML]]){const i=document.createElement('input');i.type='hidden';i.name=k;i.value=v;f.appendChild(i)}document.body.appendChild(f);f.submit();setTimeout(()=>f.remove(),1000)})()""".replace("ACTION", json.dumps(action)).replace("TOKEN", json.dumps(self.import_token))
        return script.replace("\n", "")

    @staticmethod
    def _same_url(left: str, right: str) -> bool:
        def normalize(value: str) -> str:
            parsed = urlsplit(value.strip())
            return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", parsed.query, ""))
        return normalize(left) == normalize(right)

    def accept_browser_import(self, token: str, source_url: str, html: str) -> Job:
        if not hmac.compare_digest(token, self.import_token):
            raise ValueError("浏览器导入令牌无效")
        if len(html.encode("utf-8")) > MAX_HTML_BYTES:
            raise ValueError("导入的网页 HTML 超过 5MB 限制")
        with self.lock:
            waiting = next((job for job in self.jobs.values() if job.status == "awaiting_browser_import" and self._same_url(job.url, source_url)), None)
        if waiting is None:
            raise ValueError("没有等待该 URL 浏览器导入的任务")
        waiting.status = "running"
        waiting.error = None
        waiting.event("收到浏览器导入内容")
        self.executor.submit(self._run, waiting, html)
        return waiting

    def _run(self, job: Job, imported_html: str | None = None) -> None:
        try:
            job.status = "running"
            project, _session = create_url_project(job.url, self.output_root, job.event, imported_html=imported_html)
            job.project_dir = project.output.project_dir
            job.event("渲染视频")
            video = render_project(project, self.repo_root / "remotion", project.output.final_video, on_progress=lambda message: job.event(message.split("|", 1)[-1]), quiet=True)
            job.video_path = str(video)
            job.status = "completed"
            job.event("已完成")
        except BrowserImportRequired as exc:
            job.status = "awaiting_browser_import"
            job.browser_import_status = exc.status_code
            job.error = None
            job.event(f"需要浏览器导入页面内容（HTTP {exc.status_code}）")
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
            job.event("生成失败")


def create_app(output_root: str | Path | None = None) -> FastAPI:
    repo_root = Path(__file__).resolve().parents[2]
    manager = JobManager(Path(output_root or repo_root / "output"), repo_root)
    app = FastAPI(title="URL Video Assistant")
    app.state.jobs = manager

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _PAGE

    @app.post("/api/jobs")
    def submit(payload: JobRequest, request: Request):
        job = manager.submit(payload.url, str(request.base_url).rstrip("/"))
        return _job_payload(job)

    @app.post("/api/browser-import", response_class=HTMLResponse)
    async def browser_import(request: Request):
        body = await request.body()
        if len(body) > MAX_HTML_BYTES * 2:
            raise HTTPException(413, "浏览器导入请求过大")
        try:
            fields = parse_qs(body.decode("utf-8"), keep_blank_values=True, max_num_fields=3)
            token = fields.get("token", [""])[0]
            source_url = fields.get("source_url", [""])[0]
            html = fields.get("html", [""])[0]
            if not source_url or not html:
                raise ValueError("浏览器导入缺少 URL 或 HTML")
            job = manager.accept_browser_import(token, source_url, html)
        except UnicodeDecodeError as exc:
            raise HTTPException(400, "浏览器导入内容不是有效 UTF-8") from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return HTMLResponse(f"<!doctype html><meta charset='utf-8'><title>导入完成</title><p>已导入任务 {job.id}，可以关闭此页面并返回 Video Assistant。</p>")

    @app.post("/api/browser-asset-upload")
    def browser_asset_upload():
        raise HTTPException(501, "浏览器素材上传接口已预留，当前版本尚未启用")

    @app.get("/api/jobs/{job_id}")
    def status(job_id: str):
        try:
            return _job_payload(manager.get(job_id))
        except KeyError as exc:
            raise HTTPException(404, "任务不存在") from exc

    @app.get("/api/jobs/{job_id}/events")
    async def events(job_id: str):
        try:
            job = manager.get(job_id)
        except KeyError as exc:
            raise HTTPException(404, "任务不存在") from exc
        async def stream():
            cursor = 0
            while True:
                while cursor < len(job.events):
                    yield f"data: {json.dumps(_job_payload(job), ensure_ascii=False)}\n\n"
                    cursor += 1
                if job.status in {"completed", "failed"}:
                    break
                await asyncio.sleep(0.5)
        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/api/jobs/{job_id}/video")
    def video(job_id: str):
        try:
            job = manager.get(job_id)
        except KeyError as exc:
            raise HTTPException(404, "任务不存在") from exc
        if job.status != "completed" or not job.video_path or not Path(job.video_path).is_file():
            raise HTTPException(409, "视频尚未生成")
        return FileResponse(job.video_path, media_type="video/mp4", filename="reference-reel.mp4")

    return app


def _job_payload(job: Job) -> dict:
    browser_import = None
    if job.status == "awaiting_browser_import":
        browser_import = {
            "status_code": job.browser_import_status,
            "bookmarklet_url": job.browser_import_url,
            "message": "请在正常浏览器打开该文章，点击导入书签后返回此页面。",
        }
    return {"id": job.id, "url": job.url, "status": job.status, "stage": job.stage, "error": job.error, "project_dir": job.project_dir, "video_url": f"/api/jobs/{job.id}/video" if job.status == "completed" else None, "browser_import": browser_import}


app = create_app()


_PAGE = """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>URL Video Assistant</title><style>body{margin:0;background:#111;color:#f4f4f0;font:16px -apple-system,BlinkMacSystemFont,\"PingFang SC\",sans-serif}main{max-width:760px;margin:0 auto;padding:14vh 24px 48px}h1{font-size:32px;font-weight:650;margin:0 0 12px;letter-spacing:0}p{color:#a8aaa7;margin:0 0 30px}form{display:flex;border-bottom:1px solid #686b65;gap:12px;padding-bottom:10px}input{min-width:0;flex:1;border:0;background:transparent;color:white;font:inherit;outline:none}button{border:0;background:#dce74a;color:#111;padding:9px 16px;font:inherit;font-weight:650;cursor:pointer}#status{margin-top:32px;min-height:24px;color:#dce74a;line-height:1.8}video{display:none;margin-top:24px;width:100%;max-height:70vh;background:#000}a{color:#dce74a}</style></head><body><main><h1>文章转视频</h1><p>输入公开文章 URL，自动提取正文与图片并生成竖屏短视频。</p><form id='form'><input id='url' type='url' required placeholder='https://example.com/article'><button>生成视频</button></form><div id='status'></div><video id='video' controls></video></main><script>const form=document.querySelector('#form'),input=document.querySelector('#url'),status=document.querySelector('#status'),video=document.querySelector('#video');function render(x){status.replaceChildren(document.createTextNode(x.stage));if(x.status==='awaiting_browser_import'&&x.browser_import?.bookmarklet_url){status.append(document.createTextNode(' '));const a=document.createElement('a');a.href=x.browser_import.bookmarklet_url;a.textContent='导入当前文章';a.title='将此链接拖到书签栏，在文章页面点击';a.draggable=true;status.append(a)}if(x.status==='failed'){status.append(document.createTextNode('：'+(x.error||'生成失败')))}if(x.status==='completed'){video.src=x.video_url;video.style.display='block'}}form.onsubmit=async e=>{e.preventDefault();video.style.display='none';status.textContent='正在提交任务';const r=await fetch('/api/jobs',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({url:input.value})});const j=await r.json();if(!r.ok){status.textContent=j.detail||'提交失败';return}const source=new EventSource('/api/jobs/'+j.id+'/events');source.onmessage=e=>{const x=JSON.parse(e.data);render(x);if(x.status==='failed'||x.status==='completed'){source.close()}}}</script></body></html>"""
