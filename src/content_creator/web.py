"""Local single-input web application for URL video generation."""
from __future__ import annotations

import asyncio
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from content_creator.services.renderer import render_project
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
    events: list[dict[str, str]] = field(default_factory=list)

    def event(self, stage: str) -> None:
        self.stage = stage
        self.events.append({"status": self.status, "stage": stage})


class JobRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


class JobManager:
    def __init__(self, output_root: Path, repo_root: Path):
        self.output_root, self.repo_root = output_root, repo_root
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="url-video")

    def submit(self, url: str) -> Job:
        job = Job(id=uuid.uuid4().hex, url=url)
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

    def _run(self, job: Job) -> None:
        try:
            job.status = "running"
            project, _session = create_url_project(job.url, self.output_root, job.event)
            job.project_dir = project.output.project_dir
            job.event("渲染视频")
            video = render_project(project, self.repo_root / "remotion", project.output.final_video, on_progress=lambda message: job.event(message.split("|", 1)[-1]), quiet=True)
            job.video_path = str(video)
            job.status = "completed"
            job.event("已完成")
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
    def submit(payload: JobRequest):
        job = manager.submit(payload.url)
        return _job_payload(job)

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
    return {"id": job.id, "url": job.url, "status": job.status, "stage": job.stage, "error": job.error, "project_dir": job.project_dir, "video_url": f"/api/jobs/{job.id}/video" if job.status == "completed" else None}


app = create_app()


_PAGE = """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>URL Video Assistant</title><style>body{margin:0;background:#111;color:#f4f4f0;font:16px -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}main{max-width:760px;margin:0 auto;padding:14vh 24px 48px}h1{font-size:32px;font-weight:650;margin:0 0 12px;letter-spacing:0}p{color:#a8aaa7;margin:0 0 30px}form{display:flex;border-bottom:1px solid #686b65;gap:12px;padding-bottom:10px}input{min-width:0;flex:1;border:0;background:transparent;color:white;font:inherit;outline:none}button{border:0;background:#dce74a;color:#111;padding:9px 16px;font:inherit;font-weight:650;cursor:pointer}#status{margin-top:32px;min-height:24px;color:#dce74a}video{display:none;margin-top:24px;width:100%;max-height:70vh;background:#000}a{color:#dce74a}</style></head><body><main><h1>文章转视频</h1><p>输入公开文章 URL，自动提取正文与图片并生成竖屏短视频。</p><form id='form'><input id='url' type='url' required placeholder='https://example.com/article'><button>生成视频</button></form><div id='status'></div><video id='video' controls></video></main><script>const form=document.querySelector('#form'),input=document.querySelector('#url'),status=document.querySelector('#status'),video=document.querySelector('#video');form.onsubmit=async e=>{e.preventDefault();video.style.display='none';status.textContent='正在提交任务';const r=await fetch('/api/jobs',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({url:input.value})});const j=await r.json();if(!r.ok){status.textContent=j.detail||'提交失败';return}const source=new EventSource('/api/jobs/'+j.id+'/events');source.onmessage=e=>{const x=JSON.parse(e.data);status.textContent=x.stage;if(x.status==='failed'){status.textContent='失败：'+x.error;source.close()}if(x.status==='completed'){video.src=x.video_url;video.style.display='block';source.close()}}}</script></body></html>"""
