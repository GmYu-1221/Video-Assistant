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
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, quote, urlsplit, urlunsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from content_creator.services.renderer import render_project
from content_creator.services.renderer.remotion import render_layout_still
from content_creator.services.article import BrowserImportRequired, MAX_HTML_BYTES
from content_creator.services.url_video import create_url_project
from content_creator.services.artifact_validation import validate_final_artifact
from content_creator.services.layout.preferences import TypographyPreferenceStore, article_context
from content_creator.services.layout.copy_density import detect_copy_density_intent
from content_creator.services.layout.revision import load_version_project, project_copy_metrics, project_font_ids, project_layout_fingerprints, revise_typography, write_version_snapshot
from content_creator.agents.visual_critic import critique_scene
from content_creator.schemas import ArticleBrief


@dataclass
class JobVersion:
    id: str
    video_path: str
    project_path: str
    created_at: str
    source_version: str | None = None
    feedback_id: str | None = None


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
    versions: list[JobVersion] = field(default_factory=list)
    current_version: str | None = None
    feedback_status: str | None = None
    persist_callback: Callable[[], None] | None = field(default=None, repr=False, compare=False)

    def event(self, stage: str) -> None:
        self.stage = stage
        self.events.append({"status": self.status, "stage": stage})
        if self.persist_callback:
            self.persist_callback()


class JobRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


class FeedbackRequest(BaseModel):
    version_id: str = Field(pattern=r"^v\d{3,}$")
    rating: str = Field(pattern=r"^(positive|negative)$")
    reason: str = Field(default="", max_length=1000)


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
        self.jobs_dir = self.output_root / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.preferences = TypographyPreferenceStore(self.output_root)
        self._load_jobs()

    def _job_path(self, job_id: str) -> Path:
        return self.jobs_dir / f"{job_id}.json"

    def _persist_job(self, job: Job) -> None:
        data = {
            "id": job.id, "url": job.url, "status": job.status, "stage": job.stage,
            "error": job.error, "project_dir": job.project_dir, "video_path": job.video_path,
            "browser_import_status": job.browser_import_status, "browser_import_url": job.browser_import_url,
            "events": job.events, "versions": [asdict(version) for version in job.versions],
            "current_version": job.current_version, "feedback_status": job.feedback_status,
        }
        path = self._job_path(job.id)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def _attach(self, job: Job) -> Job:
        job.persist_callback = lambda: self._persist_job(job)
        return job

    def _load_jobs(self) -> None:
        for path in self.jobs_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                versions = [JobVersion(**item) for item in data.pop("versions", [])]
                job = self._attach(Job(**data, versions=versions))
                if job.status in {"queued", "running", "revising"}:
                    job.status = "failed"
                    job.error = "服务重启中断了正在执行的任务"
                    job.stage = "任务已中断"
                    self._persist_job(job)
                self.jobs[job.id] = job
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue

    def submit(self, url: str, import_base_url: str = "http://127.0.0.1:8000") -> Job:
        job = self._attach(Job(id=uuid.uuid4().hex, url=url))
        job.browser_import_url = self.browser_import_url(import_base_url)
        with self.lock:
            self.jobs[job.id] = job
        self._persist_job(job)
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
            validation = validate_final_artifact(video)
            (Path(project.output.project_dir) / "final_artifact_validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
            if not validation["passed"]:
                raise RuntimeError("最终视频产物校验失败：" + "；".join(validation["errors"]))
            version_dir = Path(project.output.project_dir) / "versions" / "v001"
            write_version_snapshot(project, version_dir, source_project_dir=project.output.project_dir, copy_video_from=video)
            version = JobVersion(id="v001", video_path=str(version_dir / "final.mp4"), project_path=str(version_dir / "project.json"), created_at=datetime.now(timezone.utc).isoformat())
            job.versions = [version]
            job.current_version = version.id
            job.video_path = version.video_path
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

    def submit_feedback(self, job_id: str, payload: FeedbackRequest) -> Job:
        job = self.get(job_id)
        if job.status == "revising":
            raise ValueError("字幕版本正在生成，请等待当前修订完成")
        version = next((item for item in job.versions if item.id == payload.version_id), None)
        if version is None:
            raise ValueError("反馈引用的视频版本不存在")
        project = load_version_project(Path(version.project_path).parent)
        brief_path = Path(project.output.project_dir) / "article.json"
        brief = ArticleBrief.model_validate_json(brief_path.read_text(encoding="utf-8"))
        feedback_id = uuid.uuid4().hex
        record = self.preferences.append({
            "record_type": "feedback",
            "feedback_id": feedback_id, "job_id": job.id, "project_id": project.project_id,
            "version_id": version.id, "rating": payload.rating, "reason": payload.reason,
            "context": article_context(brief), "scene_purposes": sorted({item.narrative.scene_purpose for item in project.timeline if item.narrative}),
            "font_ids": project_font_ids(project), "layout_fingerprints": project_layout_fingerprints(project),
            "copy_density_intent": detect_copy_density_intent(payload.reason).value,
            "before_copy_metrics": project_copy_metrics(project),
        })
        if payload.rating == "positive":
            job.feedback_status = "recorded"
            job.error = None
            job.event("已记录你的字体与字幕偏好")
            return job
        next_version = f"v{len(job.versions) + 1:03d}"
        job.status = "revising"
        job.feedback_status = "revising"
        job.error = None
        job.event(f"根据反馈生成字幕版本 {next_version}")
        self.executor.submit(self._run_revision, job, version, next_version, record, brief)
        return job

    def _run_revision(self, job: Job, source: JobVersion, version_id: str, feedback: dict, brief: ArticleBrief) -> None:
        try:
            project = load_version_project(Path(source.project_path).parent)
            project_dir = Path(project.output.project_dir)
            version_dir = project_dir / "versions" / version_id
            job.event("Layout Director 正在重新设计字体与字幕")
            revised, artifacts = revise_typography(
                project, revision_id=version_id, reason=feedback.get("reason", ""),
                context=article_context(brief), preferences=self.preferences.summary_for(brief),
                remotion_public=self.repo_root / "remotion" / "public",
                article=brief,
            )
            write_version_snapshot(revised, version_dir, source_project_dir=project_dir)
            (version_dir / "layout_plan.json").write_text(artifacts["layout_plan"].model_dump_json(indent=2), encoding="utf-8")
            (version_dir / "scene_narrative_plan.json").write_text(json.dumps({"persistent_title": revised.persistent_title.model_dump(mode="json") if revised.persistent_title else None, "narratives": [item.narrative.model_dump(mode="json") for item in revised.timeline if item.narrative]}, ensure_ascii=False, indent=2), encoding="utf-8")
            qa = artifacts["layout_qa"]
            for item, record in zip(revised.timeline, qa["segments"]):
                frame = min(item.end_frame - 1, item.start_frame + max(12, item.duration_frames // 2))
                preview = render_layout_still(revised, self.repo_root / "remotion", version_dir / "layout" / "previews" / item.resolved_state.segment_id / "middle.png", frame)
                critic = critique_scene(rendered_ok=True, hard_issues=[], preview_paths=[str(preview)], scene_purpose=item.narrative.scene_purpose)
                record["preview_path"] = str(preview)
                record["visual_critic"] = critic.model_dump(mode="json")
            (version_dir / "layout_qa.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")
            feedback_result = feedback | {"copy_density": qa.get("copy_density", {})}
            (version_dir / "feedback.json").write_text(json.dumps(feedback_result, ensure_ascii=False, indent=2), encoding="utf-8")
            target = version_dir / "final.mp4"
            job.event(f"渲染字幕版本 {version_id}")
            video = render_project(revised, self.repo_root / "remotion", target, on_progress=lambda message: job.event(message.split("|", 1)[-1]), quiet=True)
            validation = validate_final_artifact(video)
            (version_dir / "final_artifact_validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
            if not validation["passed"]:
                raise RuntimeError("字幕版本产物校验失败：" + "；".join(validation["errors"]))
            version = JobVersion(id=version_id, video_path=str(video), project_path=str(version_dir / "project.json"), created_at=datetime.now(timezone.utc).isoformat(), source_version=source.id, feedback_id=feedback["feedback_id"])
            job.versions.append(version)
            job.current_version = version.id
            job.video_path = version.video_path
            job.feedback_status = "completed"
            job.status = "completed"
            job.error = None
            self.preferences.append({
                "record_type": "revision_outcome", "feedback_id": feedback["feedback_id"],
                "job_id": job.id, "project_id": project.project_id, "version_id": version_id,
                "copy_density_intent": feedback.get("copy_density_intent", "preserve"),
                "copy_metrics": qa.get("copy_density", {}),
            })
            job.event(f"字幕版本 {version_id} 已完成")
        except Exception as exc:
            job.status = "completed"
            job.feedback_status = "failed"
            job.error = str(exc)
            job.event("字幕修订失败，已保留原视频")


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

    @app.post("/api/jobs/{job_id}/feedback")
    def feedback(job_id: str, payload: FeedbackRequest):
        try:
            return _job_payload(manager.submit_feedback(job_id, payload))
        except KeyError as exc:
            raise HTTPException(404, "任务不存在") from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

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
    def video(job_id: str, version: str | None = None):
        try:
            job = manager.get(job_id)
        except KeyError as exc:
            raise HTTPException(404, "任务不存在") from exc
        selected = next((item for item in job.versions if item.id == (version or job.current_version)), None)
        video_path = selected.video_path if selected else job.video_path
        if not video_path or not Path(video_path).is_file():
            raise HTTPException(409, "视频尚未生成")
        return FileResponse(video_path, media_type="video/mp4", filename=f"reference-reel-{selected.id if selected else 'latest'}.mp4", headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"})

    return app


def _job_payload(job: Job) -> dict:
    browser_import = None
    if job.status == "awaiting_browser_import":
        browser_import = {
            "status_code": job.browser_import_status,
            "bookmarklet_url": job.browser_import_url,
            "message": "请在正常浏览器打开该文章，点击导入书签后返回此页面。",
        }
    versions = [{"id": item.id, "created_at": item.created_at, "source_version": item.source_version, "video_url": f"/api/jobs/{job.id}/video?version={item.id}"} for item in job.versions]
    return {"id": job.id, "url": job.url, "status": job.status, "stage": job.stage, "error": job.error, "project_dir": job.project_dir, "video_url": f"/api/jobs/{job.id}/video?version={job.current_version}" if job.current_version else None, "versions": versions, "current_version": job.current_version, "feedback_status": job.feedback_status, "browser_import": browser_import}


app = create_app()


_PAGE = """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>URL Video Assistant</title><style>body{margin:0;background:#111;color:#f4f4f0;font:16px -apple-system,BlinkMacSystemFont,\"PingFang SC\",sans-serif}main{max-width:760px;margin:0 auto;padding:14vh 24px 48px}h1{font-size:32px;font-weight:650;margin:0 0 12px;letter-spacing:0}p{color:#a8aaa7;margin:0 0 30px}form{display:flex;border-bottom:1px solid #686b65;gap:12px;padding-bottom:10px}input{min-width:0;flex:1;border:0;background:transparent;color:white;font:inherit;outline:none}button{border:0;background:#dce74a;color:#111;padding:9px 16px;font:inherit;font-weight:650;cursor:pointer}#status{margin-top:32px;min-height:24px;color:#dce74a;line-height:1.8}video{display:none;margin-top:24px;width:100%;max-height:70vh;background:#000}a{color:#dce74a}</style></head><body><main><h1>文章转视频</h1><p>输入公开文章 URL，自动提取正文与图片并生成竖屏短视频。</p><form id='form'><input id='url' type='url' required placeholder='https://example.com/article'><button>生成视频</button></form><div id='status'></div><video id='video' controls></video></main><script>const form=document.querySelector('#form'),input=document.querySelector('#url'),status=document.querySelector('#status'),video=document.querySelector('#video');function render(x){status.replaceChildren(document.createTextNode(x.stage));if(x.status==='awaiting_browser_import'&&x.browser_import?.bookmarklet_url){status.append(document.createTextNode(' '));const a=document.createElement('a');a.href=x.browser_import.bookmarklet_url;a.textContent='导入当前文章';a.title='将此链接拖到书签栏，在文章页面点击';a.draggable=true;status.append(a)}if(x.status==='failed'){status.append(document.createTextNode('：'+(x.error||'生成失败')))}if(x.status==='completed'){video.src=x.video_url;video.style.display='block'}}form.onsubmit=async e=>{e.preventDefault();video.style.display='none';status.textContent='正在提交任务';const r=await fetch('/api/jobs',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({url:input.value})});const j=await r.json();if(!r.ok){status.textContent=j.detail||'提交失败';return}const source=new EventSource('/api/jobs/'+j.id+'/events');source.onmessage=e=>{const x=JSON.parse(e.data);render(x);if(x.status==='failed'||x.status==='completed'){source.close()}}}</script></body></html>"""
_PAGE = _PAGE.replace("video{display:none;margin-top:24px;width:100%;max-height:70vh", "video{display:none;margin:24px auto 0;width:min(100%,405px);aspect-ratio:9/16;object-fit:contain")
_PAGE = _PAGE.replace("function render(x){", "function resetVideo(){video.pause();video.removeAttribute('src');video.load();video.style.display='none'}function render(x){")
_PAGE = _PAGE.replace("video.src=x.video_url;video.style.display='block'", "video.src=x.video_url+'?v='+encodeURIComponent(x.id);video.load();video.style.display='block';status.append(document.createTextNode(' · 任务 '+x.id+' · 1080×1920'))")
_PAGE = _PAGE.replace("e.preventDefault();video.style.display='none';status.textContent", "e.preventDefault();resetVideo();status.textContent")

# The page stays dependency-free, but exposes versioned typography feedback.
_PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>URL Video Assistant</title><style>
body{margin:0;background:#111;color:#f4f4f0;font:16px -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;letter-spacing:0}
main{max-width:760px;margin:0 auto;padding:10vh 24px 48px}h1{font-size:32px;margin:0 0 12px}p{color:#a8aaa7;margin:0 0 28px}
#generate{display:flex;border-bottom:1px solid #686b65;gap:12px;padding-bottom:10px}input,textarea,select{font:inherit;color:#f4f4f0;background:#1b1d1c;border:1px solid #4d504c}
#url{min-width:0;flex:1;border:0;background:transparent;outline:none}button{border:0;background:#dce74a;color:#111;padding:9px 16px;font:inherit;font-weight:650;cursor:pointer}button.secondary{background:#2a2d2a;color:#f4f4f0;border:1px solid #555}
#status{margin-top:28px;min-height:24px;color:#dce74a;line-height:1.7}video{display:none;margin:22px auto 0;width:min(100%,405px);aspect-ratio:9/16;object-fit:contain;background:#000}
#review{display:none;margin-top:24px;padding-top:20px;border-top:1px solid #383b38}#versionRow{display:flex;align-items:center;gap:10px;margin-bottom:16px}select{padding:8px 10px}
textarea{box-sizing:border-box;width:100%;min-height:76px;padding:10px;resize:vertical}#ratingButtons{display:flex;gap:10px;margin-top:10px}#feedbackMessage{margin-top:10px;color:#a8aaa7}a{color:#dce74a}
</style></head><body><main><h1>文章转视频</h1><p>输入公开文章 URL，自动生成竖屏短视频，并通过反馈学习你的字幕审美。</p>
<form id="generate"><input id="url" type="url" required placeholder="https://example.com/article"><button>生成视频</button></form>
<div id="status"></div><video id="video" controls></video>
<section id="review"><div id="versionRow"><label for="versions">视频版本</label><select id="versions"></select></div>
<textarea id="reason" maxlength="1000" placeholder="可选：例如字太花、标题太挤、层级不清楚"></textarea>
<div id="ratingButtons"><button type="button" data-rating="positive">好看</button><button type="button" class="secondary" data-rating="negative">不好看，重新设计字幕</button></div><div id="feedbackMessage"></div></section>
</main><script>
const form=document.querySelector('#generate'),urlInput=document.querySelector('#url'),statusEl=document.querySelector('#status'),video=document.querySelector('#video'),review=document.querySelector('#review'),versions=document.querySelector('#versions'),reason=document.querySelector('#reason'),feedbackMessage=document.querySelector('#feedbackMessage');
let currentJob=null,eventSource=null;
function setVideo(src){if(!src)return;video.pause();video.src=src+'&cache='+Date.now();video.load();video.style.display='block'}
function render(job){currentJob=job;statusEl.textContent=job.stage||job.status;if(job.error)statusEl.textContent+='：'+job.error;if(job.status==='awaiting_browser_import'&&job.browser_import?.bookmarklet_url){const a=document.createElement('a');a.href=job.browser_import.bookmarklet_url;a.textContent=' 导入当前文章';a.draggable=true;statusEl.append(a)}
const old=versions.value;versions.replaceChildren(...job.versions.map(v=>{const o=document.createElement('option');o.value=v.id;o.textContent=v.id+(v.id===job.current_version?'（当前）':'');o.dataset.url=v.video_url;return o}));if(job.versions.length){versions.value=job.versions.some(v=>v.id===old)?old:job.current_version;review.style.display='block';const selected=job.versions.find(v=>v.id===versions.value);if(selected&&video.dataset.version!==selected.id){video.dataset.version=selected.id;setVideo(selected.video_url)}}else{review.style.display='none'}
document.querySelectorAll('[data-rating]').forEach(b=>b.disabled=job.status==='revising');if(job.feedback_status==='revising')feedbackMessage.textContent='正在生成新的字幕版本';else if(job.feedback_status==='completed')feedbackMessage.textContent='新字幕版本已生成';else if(job.feedback_status==='recorded')feedbackMessage.textContent='已记录偏好，将影响以后的视频';else if(job.feedback_status==='failed')feedbackMessage.textContent='修订失败：'+(job.error||'未知布局错误')+'；原视频仍然保留';}
function listen(id){eventSource?.close();eventSource=new EventSource('/api/jobs/'+id+'/events');eventSource.onmessage=e=>{const job=JSON.parse(e.data);render(job);if(job.status==='completed'||job.status==='failed')eventSource.close()}}
form.onsubmit=async e=>{e.preventDefault();video.style.display='none';review.style.display='none';statusEl.textContent='正在提交任务';const response=await fetch('/api/jobs',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({url:urlInput.value})});const job=await response.json();if(!response.ok){statusEl.textContent=job.detail||'提交失败';return}render(job);listen(job.id)};
versions.onchange=()=>{const selected=currentJob?.versions.find(v=>v.id===versions.value);if(selected){video.dataset.version=selected.id;setVideo(selected.video_url)}};
document.querySelectorAll('[data-rating]').forEach(button=>button.onclick=async()=>{if(!currentJob)return;feedbackMessage.textContent='正在提交反馈';const response=await fetch('/api/jobs/'+currentJob.id+'/feedback',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({version_id:versions.value,rating:button.dataset.rating,reason:reason.value})});const job=await response.json();if(!response.ok){feedbackMessage.textContent=job.detail||'反馈提交失败';return}render(job);if(button.dataset.rating==='negative')listen(job.id);else reason.value=''})
</script></body></html>"""
