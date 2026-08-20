"""Local Web UI for the multi-source HTML animation video pipeline."""
from __future__ import annotations

import asyncio
import hmac
import json
import os
import secrets
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlsplit, urlunsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field, ValidationError, field_validator

from content_creator.config import PROJECT_ROOT
from content_creator.schemas import ProjectContext
from content_creator.services.article import BrowserImportRequired, MAX_HTML_BYTES
from content_creator.services.url_video import create_project_context, run_url_video_project


STAGE_PROGRESS = {
    "等待开始": 0, "文章处理": 10, "内容编排": 25, "导演设计": 42,
    "文案适配": 55, "分页编译": 63, "导演复核": 70, "动画生成": 79, "视频渲染": 85, "完成": 100,
}


def _public_error_message(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "；".join(".".join(map(str, error["loc"])) + "：" + error["msg"] for error in exc.errors(include_url=False, include_input=False)[:4])
    return (str(exc).strip() or type(exc).__name__).split(" For further information visit ", 1)[0]


class JobRequest(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=3)

    @field_validator("urls")
    @classmethod
    def normalize_urls(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            value = value.strip()
            parsed = urlsplit(value)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
                raise ValueError("每项都必须是公开 HTTP 或 HTTPS URL")
            normalized = urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", parsed.query, ""))
            if normalized not in result:
                result.append(normalized)
        if not result:
            raise ValueError("至少需要一个 URL")
        return result


@dataclass
class BrowserImport:
    source_id: str
    url: str
    status_code: int
    status: str = "waiting"


@dataclass
class Job:
    id: str
    urls: list[str]
    status: str = "queued"
    stage: str = "等待开始"
    progress: int = 0
    error: str | None = None
    project_dir: str | None = None
    video_path: str | None = None
    browser_imports: list[BrowserImport] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    persist_callback: Callable[[], None] | None = field(default=None, repr=False, compare=False)

    def event(self, stage: str) -> None:
        self.stage = stage
        base = next((value for name, value in STAGE_PROGRESS.items() if stage.startswith(name)), self.progress)
        if stage.startswith("视频渲染 ") and "/" in stage:
            try:
                current, total = stage.rsplit(" ", 1)[1].split("/", 1)
                base = 85 + int(int(current) / max(1, int(total)) * 14)
            except ValueError:
                pass
        self.progress = max(self.progress, min(100, base))
        self.events.append({"status": self.status, "stage": stage, "progress": self.progress})
        if self.persist_callback:
            self.persist_callback()


class JobManager:
    def __init__(self, output_root: Path):
        self.output_root = output_root.resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.jobs_dir = self.output_root / "jobs"
        self.jobs_dir.mkdir(exist_ok=True)
        self.token_path = self.output_root / ".browser-import-token"
        if self.token_path.is_file():
            self.import_token = self.token_path.read_text(encoding="utf-8").strip()
        else:
            self.import_token = secrets.token_urlsafe(32)
            self.token_path.write_text(self.import_token, encoding="utf-8")
            os.chmod(self.token_path, 0o600)
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="video-job")
        self._load_jobs()

    def _path(self, job_id: str) -> Path:
        return self.jobs_dir / f"{job_id}.json"

    def _attach(self, job: Job) -> Job:
        job.persist_callback = lambda: self._persist(job)
        return job

    def _persist(self, job: Job) -> None:
        value = {
            "id": job.id, "urls": job.urls, "status": job.status, "stage": job.stage,
            "progress": job.progress, "error": job.error, "project_dir": job.project_dir,
            "video_path": job.video_path, "events": job.events,
            "browser_imports": [item.__dict__ for item in job.browser_imports],
        }
        path = self._path(job.id)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def _load_jobs(self) -> None:
        for path in self.jobs_dir.glob("*.json"):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                imports = [BrowserImport(**item) for item in value.pop("browser_imports", [])]
                job = self._attach(Job(**value, browser_imports=imports))
                if job.status in {"queued", "running"}:
                    job.status, job.stage, job.error = "failed", "任务中断", "服务重启中断了任务"
                    self._persist(job)
                self.jobs[job.id] = job
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue

    def submit(self, urls: list[str]) -> Job:
        job = self._attach(Job(id=uuid.uuid4().hex, urls=urls))
        context = create_project_context(job.id, urls, self.output_root)
        job.project_dir = context.project_dir
        with self.lock:
            self.jobs[job.id] = job
        self._persist(job)
        self.executor.submit(self._run, job)
        return job

    def get(self, job_id: str) -> Job:
        with self.lock:
            job = self.jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def _context(self, job: Job) -> ProjectContext:
        if not job.project_dir:
            raise RuntimeError("Job has no project directory")
        path = Path(job.project_dir) / "project.json"
        context = ProjectContext.model_validate_json(path.read_text(encoding="utf-8"))
        imports = {}
        for item in job.browser_imports:
            imported = Path(job.project_dir) / "sources" / item.source_id / "imported.html"
            if imported.is_file():
                imports[item.source_id] = imported.read_text(encoding="utf-8")
        return context.model_copy(update={"imported_html": imports})

    def _run(self, job: Job) -> None:
        try:
            job.status, job.error = "running", None
            job.event("文章处理")
            video = run_url_video_project(self._context(job), on_progress=job.event)
            job.video_path = str(video)
            job.status = "completed"
            job.event("完成")
        except BrowserImportRequired as exc:
            source_id = next((f"source-{index:03d}" for index, url in enumerate(job.urls, 1) if self._same_url(url, exc.url)), "source-001")
            existing = next((item for item in job.browser_imports if item.source_id == source_id), None)
            if existing:
                existing.status_code, existing.status = exc.status_code, "waiting"
            else:
                job.browser_imports.append(BrowserImport(source_id, exc.url, exc.status_code))
            job.status, job.error = "waiting_browser_import", None
            job.event(f"文章处理：{source_id} 等待浏览器导入")
        except Exception as exc:
            job.status, job.error = "failed", _public_error_message(exc)
            job.event("生成失败")

    @staticmethod
    def _same_url(left: str, right: str) -> bool:
        def normalized(value: str) -> str:
            parsed = urlsplit(value.strip())
            return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", parsed.query, ""))
        return normalized(left) == normalized(right)

    def bookmarklet(self, base_url: str) -> str:
        action = base_url.rstrip("/") + "/api/browser-import"
        script = "javascript:(()=>{const f=document.createElement('form');f.method='POST';f.action=ACTION;f.target='_blank';for(const[k,v]of[['token',TOKEN],['source_url',location.href],['html',document.documentElement.outerHTML]]){const i=document.createElement('input');i.type='hidden';i.name=k;i.value=v;f.appendChild(i)}document.body.appendChild(f);f.submit()})()"
        return script.replace("ACTION", json.dumps(action)).replace("TOKEN", json.dumps(self.import_token))

    def accept_browser_import(self, token: str, source_url: str, html: str) -> Job:
        if not hmac.compare_digest(token, self.import_token):
            raise ValueError("浏览器导入令牌无效")
        if len(html.encode("utf-8")) > MAX_HTML_BYTES:
            raise ValueError("导入 HTML 超过 5MB")
        with self.lock:
            match = next(((job, item) for job in self.jobs.values() for item in job.browser_imports if job.status == "waiting_browser_import" and item.status == "waiting" and self._same_url(item.url, source_url)), None)
        if match is None:
            raise ValueError("没有等待该 URL 的任务")
        job, item = match
        target = Path(job.project_dir) / "sources" / item.source_id / "imported.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding="utf-8")
        item.status = "received"
        job.status = "running"
        job.event(f"文章处理：收到 {item.source_id} 浏览器内容")
        self.executor.submit(self._run, job)
        return job


def _job_payload(job: Job, base_url: str = "http://127.0.0.1:8000", manager: JobManager | None = None) -> dict:
    imports = [item.__dict__ | ({"bookmarklet_url": manager.bookmarklet(base_url)} if manager and item.status == "waiting" else {}) for item in job.browser_imports]
    return {
        "id": job.id, "urls": job.urls, "status": job.status, "stage": job.stage,
        "progress": job.progress, "error": job.error, "project_dir": job.project_dir,
        "browser_imports": imports,
        "video_url": f"/api/jobs/{job.id}/video" if job.video_path else None,
    }


def create_app(output_root: str | Path | None = None) -> FastAPI:
    manager = JobManager(Path(output_root or PROJECT_ROOT / "output"))
    app = FastAPI(title="Video Assistant")
    app.state.jobs = manager

    @app.get("/", response_class=HTMLResponse)
    def index():
        return _PAGE

    @app.post("/api/jobs")
    def create_job(payload: JobRequest):
        return _job_payload(manager.submit(payload.urls), manager=manager)

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        try:
            return _job_payload(manager.get(job_id), manager=manager)
        except KeyError:
            raise HTTPException(404, "任务不存在")

    @app.get("/api/jobs/{job_id}/events")
    async def events(job_id: str):
        try:
            manager.get(job_id)
        except KeyError:
            raise HTTPException(404, "任务不存在")

        async def stream():
            previous = None
            while True:
                job = manager.get(job_id)
                payload = json.dumps(_job_payload(job, manager=manager), ensure_ascii=False)
                if payload != previous:
                    yield f"data: {payload}\n\n"
                    previous = payload
                if job.status in {"completed", "failed"}:
                    return
                await asyncio.sleep(.5)
        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/api/jobs/{job_id}/video")
    def video(job_id: str):
        try:
            job = manager.get(job_id)
        except KeyError:
            raise HTTPException(404, "任务不存在")
        if not job.video_path or not Path(job.video_path).is_file():
            raise HTTPException(404, "视频尚未生成")
        return FileResponse(job.video_path, media_type="video/mp4", filename=f"{job.id}.mp4")

    @app.post("/api/browser-import", response_class=HTMLResponse)
    async def browser_import(request: Request):
        values = parse_qs((await request.body()).decode("utf-8", "replace"), keep_blank_values=True)
        try:
            job = manager.accept_browser_import(values.get("token", [""])[0], values.get("source_url", [""])[0], values.get("html", [""])[0])
            return f"<!doctype html><meta charset=utf-8><title>导入成功</title><p>已导入任务 {job.id}，可以关闭此页面。</p>"
        except ValueError as exc:
            raise HTTPException(400, str(exc))
    return app


app = create_app()


_PAGE = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Video Assistant</title><style>
:root{color-scheme:dark;--bg:#0d1014;--panel:#171c23;--line:#343c46;--text:#f2f4ee;--muted:#9199a2;--accent:#dce74a;--bad:#ef9188}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}main{width:min(760px,calc(100% - 28px));margin:7vh auto}.panel{padding:30px;background:var(--panel);border:1px solid #29313a;border-radius:10px}h1{margin:0 0 6px;font-size:30px}p{margin:0 0 24px;color:var(--muted)}form{display:grid;gap:10px}input{width:100%;height:48px;padding:0 14px;color:var(--text);background:#101419;border:1px solid var(--line);border-radius:6px;font:inherit}button{height:48px;border:0;border-radius:6px;background:var(--accent);font-weight:700;cursor:pointer}button:disabled{opacity:.5}#status{margin-top:20px;padding:16px;background:#11161c;border-radius:6px}#status[hidden]{display:none}.bar{height:7px;margin:10px 0;background:#29313a;border-radius:9px;overflow:hidden}.bar i{display:block;width:0;height:100%;background:var(--accent)}.stages{display:grid;grid-template-columns:repeat(8,1fr);gap:6px;margin-top:18px;color:var(--muted);font-size:11px;text-align:center}.stages span.active{color:var(--accent)}video{display:block;width:min(100%,420px);margin:24px auto 0;background:#000;aspect-ratio:9/16}a{color:var(--accent)}@media(max-width:620px){.panel{padding:20px}.stages{grid-template-columns:repeat(2,1fr)}}
</style></head><body><main><section class="panel"><h1>文章转视频</h1><p>输入 1～3 个文章 URL，生成 HTML / GSAP 竖屏视频。</p><form id="form"><input class="url" type="url" required placeholder="URL 1"><input class="url" type="url" placeholder="URL 2（可选）"><input class="url" type="url" placeholder="URL 3（可选）"><button id="submit">生成视频</button></form><section id="status" hidden aria-live="polite"><strong id="stage"></strong><div class="bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><i></i></div><small id="detail"></small></section><div class="stages">文章处理 · 内容编排 · 导演设计 · 文案适配 · 分页编译 · 导演复核 · 动画生成 · 视频渲染 · 完成</div><video id="video" controls playsinline hidden></video></section></main><script>
const form=document.querySelector('#form'),button=document.querySelector('#submit'),card=document.querySelector('#status'),stage=document.querySelector('#stage'),detail=document.querySelector('#detail'),bar=document.querySelector('.bar'),fill=document.querySelector('.bar i'),video=document.querySelector('#video');let es;
function render(job){card.hidden=false;stage.textContent=job.stage;detail.textContent=job.error||'';fill.style.width=job.progress+'%';bar.setAttribute('aria-valuenow',job.progress);button.disabled=['queued','running'].includes(job.status);if(job.status==='waiting_browser_import'){const waiting=job.browser_imports.find(x=>x.status==='waiting');if(waiting){detail.replaceChildren(document.createTextNode(waiting.source_id+' 需要浏览器导入。把此链接拖到书签栏： '));const a=document.createElement('a');a.href=waiting.bookmarklet_url;a.textContent='导入当前文章';detail.append(a)}}if(job.video_url){video.hidden=false;video.src=job.video_url+'?t='+Date.now()}}
form.onsubmit=async e=>{e.preventDefault();video.hidden=true;const urls=[...document.querySelectorAll('.url')].map(x=>x.value.trim()).filter(Boolean);button.disabled=true;const response=await fetch('/api/jobs',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({urls})});const job=await response.json();if(!response.ok){render({stage:'提交失败',progress:0,status:'failed',error:job.detail,browser_imports:[]});return}render(job);es?.close();es=new EventSource('/api/jobs/'+job.id+'/events');es.onmessage=event=>{const value=JSON.parse(event.data);render(value);if(['completed','failed'].includes(value.status))es.close()}}
</script></body></html>"""
