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
from pydantic import BaseModel, Field, ValidationError

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


def _public_error_message(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        fields = []
        for error in exc.errors(include_url=False, include_input=False)[:4]:
            location = ".".join(str(part) for part in error.get("loc", ())) or "data"
            fields.append(f"{location}：{error.get('msg', '数据不合法')}")
        return "生成数据校验失败：" + "；".join(fields)
    message = str(exc).strip() or type(exc).__name__
    return message.split(" For further information visit ", 1)[0]


@dataclass
class JobVersion:
    id: str
    video_path: str
    project_path: str
    created_at: str
    source_version: str | None = None
    feedback_id: str | None = None


def _stage_progress(stage: str, status: str, current: int) -> int:
    if status == "completed":
        return 100
    milestones = (
        (("等待开始", "正在提交"), 2),
        (("抓取文章", "解析浏览器导入"), 8),
        (("正文识别", "收到浏览器导入"), 15),
        (("发现网页素材",), 22),
        (("过滤网页素材",), 27),
        (("生成候选图片缩略图",), 31),
        (("识别候选图片语义", "分析网页素材"), 36),
        (("全局排序网页素材",), 40),
        (("下载已选素材",), 45),
        (("素材状态",), 48),
        (("正文截图", "补充正文截图", "准备正文截图"), 55),
        (("合并候选图片语义", "分析图片与生成文案"), 62),
        (("翻译中文说明文案",), 69),
        (("Viral Writer 正在策划",), 72),
        (("选择背景音乐",), 74),
        (("Director 编排",), 79),
        (("编排动态布局视频",), 85),
        (("根据反馈生成字幕版本",), 12),
        (("Layout Director 正在重新设计",), 38),
        (("渲染字幕版本", "渲染视频", "正式渲染开始"), 88),
        (("正在打包 Remotion",), 92),
        (("正在渲染并编码",), 96),
        (("视频渲染已完成", "字幕版本", "已完成"), 100),
    )
    matched = next((value for needles, value in milestones if any(needle in stage for needle in needles)), current)
    return max(current, matched)


@dataclass
class Job:
    id: str
    url: str
    status: str = "queued"
    stage: str = "等待开始"
    progress: int = 0
    error: str | None = None
    project_dir: str | None = None
    video_path: str | None = None
    browser_import_status: int | None = None
    browser_import_url: str | None = None
    events: list[dict[str, str | int]] = field(default_factory=list)
    versions: list[JobVersion] = field(default_factory=list)
    current_version: str | None = None
    feedback_status: str | None = None
    persist_callback: Callable[[], None] | None = field(default=None, repr=False, compare=False)

    def event(self, stage: str) -> None:
        self.stage = stage
        self.progress = _stage_progress(stage, self.status, self.progress)
        self.events.append({"status": self.status, "stage": stage, "progress": self.progress})
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
            "progress": job.progress,
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
            job.error = _public_error_message(exc)
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
        job.progress = 5
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
            job.error = _public_error_message(exc)
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
    return {"id": job.id, "url": job.url, "status": job.status, "stage": job.stage, "progress": job.progress, "error": job.error, "project_dir": job.project_dir, "video_url": f"/api/jobs/{job.id}/video?version={job.current_version}" if job.current_version else None, "versions": versions, "current_version": job.current_version, "feedback_status": job.feedback_status, "browser_import": browser_import}


app = create_app()


# The page stays dependency-free and keeps all generation state in the job API.
_PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>文章转视频</title><style>
:root{color-scheme:dark;--bg:#0d1014;--panel:#151a21;--surface:#1b2129;--surface-2:#202730;--line:#343c46;--text:#f1f3ed;--muted:#929aa3;--accent:#dce74a;--success:#45b879;--danger:#e07369}
*{box-sizing:border-box}body{margin:0;min-height:100vh;background:var(--bg);color:var(--text);font:15px/1.5 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei","Segoe UI",sans-serif;letter-spacing:0}
body:before{content:"";position:fixed;inset:0;pointer-events:none;background:linear-gradient(rgba(255,255,255,.018) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.018) 1px,transparent 1px);background-size:32px 32px;mask-image:linear-gradient(to bottom,black,transparent 70%)}
main{position:relative;width:min(880px,calc(100% - 32px));margin:0 auto;padding:9vh 0 56px}.panel{background:rgba(21,26,33,.96);border:1px solid #29313a;border-radius:8px;box-shadow:0 28px 70px rgba(0,0,0,.42);overflow:hidden}
.header{padding:30px 32px 24px;border-bottom:1px solid #29313a}.eyebrow{display:flex;align-items:center;gap:8px;color:var(--accent);font-size:12px;font-weight:700;text-transform:uppercase}.eyebrow:before{content:"";width:7px;height:7px;background:var(--accent);border-radius:50%}.header h1{margin:8px 0 4px;font-size:30px;line-height:1.25;font-weight:680}.header p{margin:0;color:var(--muted);font-size:14px}
.workspace{padding:26px 32px 30px}#generate{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px}.urlField{display:flex;align-items:center;gap:10px;min-width:0;height:48px;padding:0 14px;background:#101419;border:1px solid var(--line);border-radius:6px;transition:border-color .2s,box-shadow .2s}.urlField:focus-within{border-color:var(--accent);box-shadow:0 0 0 3px rgba(220,231,74,.09)}.linkIcon{width:20px;color:#68717b;font-size:19px;line-height:1}#url{min-width:0;width:100%;border:0;outline:0;background:transparent;color:var(--text);font:inherit}#url::placeholder{color:#606974}
button,select,textarea{font:inherit}button{height:48px;border:1px solid transparent;border-radius:6px;padding:0 20px;background:var(--accent);color:#11140e;font-weight:700;cursor:pointer;transition:transform .15s,background .15s,border-color .15s}button:hover:not(:disabled){background:#e8f35a;transform:translateY(-1px)}button:active:not(:disabled){transform:translateY(0)}button:disabled{cursor:not-allowed;opacity:.48}.generateLabel{display:inline-flex;align-items:center;gap:8px}.generateLabel:before{content:"▶";font-size:11px}
#statusCard{margin-top:20px;padding:16px;background:var(--surface);border:1px solid #2b333c;border-radius:6px}#statusCard[hidden]{display:none}.statusTop{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:12px}.statusIdentity{display:flex;align-items:center;min-width:0;gap:10px}.statusBadge{flex:none;padding:3px 9px;border-radius:4px;background:#293039;color:#c7cdd3;font-size:12px;font-weight:700}.statusBadge.running{background:rgba(220,231,74,.12);color:var(--accent)}.statusBadge.completed{background:rgba(69,184,121,.14);color:#72d69e}.statusBadge.failed{background:rgba(224,115,105,.14);color:#ef9188}.statusBadge.paused{background:rgba(211,174,91,.14);color:#e4bd68}#status{min-width:0;color:#d7dbe0;white-space:normal;overflow-wrap:anywhere}.versionPill{flex:none;color:var(--muted);font-size:12px}
#progressMeta{display:flex;justify-content:space-between;color:var(--muted);font-size:12px;margin-bottom:7px}#progressTrack{height:7px;background:#0f1318;border-radius:4px;overflow:hidden}#progressBar{width:0;height:100%;background:var(--accent);border-radius:4px;transition:width .35s ease}#progressWrap.failed #progressBar{background:var(--danger)}#progressWrap.paused #progressBar{background:#d3ae5b}a{color:var(--accent);text-underline-offset:3px}
.resultGrid{display:grid;grid-template-columns:minmax(260px,405px) minmax(0,1fr);gap:24px;align-items:start;margin-top:24px}.resultGrid:not(.ready){display:block}.videoFrame{display:none;padding:8px;background:#090b0e;border:1px solid #2b333c;border-radius:6px}.resultGrid.ready .videoFrame{display:block}video{display:block;width:100%;aspect-ratio:9/16;object-fit:contain;background:#000}
#review{display:none;padding:18px;background:var(--surface);border:1px solid #2b333c;border-radius:6px}.reviewTitle{margin:0 0 14px;font-size:15px}.fieldLabel{display:block;margin-bottom:7px;color:var(--muted);font-size:12px}#versionRow{margin-bottom:14px}select,textarea{width:100%;border:1px solid var(--line);border-radius:6px;background:#101419;color:var(--text);outline:0}select{height:40px;padding:0 10px}textarea{min-height:106px;padding:11px 12px;resize:vertical;line-height:1.55}select:focus,textarea:focus{border-color:var(--accent)}#ratingButtons{display:grid;grid-template-columns:1fr 1.5fr;gap:8px;margin-top:10px}#ratingButtons button{height:42px;padding:0 12px}.positive{background:#26362d;color:#8ae0ad;border-color:#355b43}.secondary{background:#252a31;color:#e0e3e6;border-color:#3a424c}#feedbackMessage{min-height:22px;margin-top:10px;color:var(--muted);font-size:12px}
.pipeline{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;margin-top:22px;background:#2a323b;border:1px solid #2a323b;border-radius:6px;overflow:hidden}.pipeline span{padding:10px;background:#171c23;color:#7f8892;text-align:center;font-size:11px}.pipeline b{display:block;margin-bottom:2px;color:#c6ccd2;font-size:12px}
@media(max-width:720px){main{width:min(100% - 20px,560px);padding:18px 0 32px}.header,.workspace{padding-left:18px;padding-right:18px}.header h1{font-size:25px}#generate{grid-template-columns:1fr}#generate button{width:100%}.statusTop{align-items:flex-start}.resultGrid.ready{grid-template-columns:1fr}.videoFrame{width:min(100%,360px);margin:0 auto}.pipeline{grid-template-columns:1fr 1fr}#ratingButtons{grid-template-columns:1fr}.versionPill{display:none}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important}}
</style></head><body><main><section class="panel"><header class="header"><div class="eyebrow">本地生成工作台</div><h1>文章转视频</h1><p>输入公开文章 URL，生成中文竖屏短视频。</p></header><div class="workspace">
<form id="generate"><label class="urlField" for="url"><span class="linkIcon" aria-hidden="true">⌁</span><input id="url" type="url" required autocomplete="url" placeholder="https://example.com/article"></label><button id="generateButton"><span class="generateLabel">生成视频</span></button></form>
<section id="statusCard" aria-live="polite" hidden><div class="statusTop"><div class="statusIdentity"><span id="statusBadge" class="statusBadge">等待</span><span id="status"></span></div><span id="versionPill" class="versionPill"></span></div><div id="progressWrap"><div id="progressMeta"><span>任务进度</span><span id="progressValue">0%</span></div><div id="progressTrack" role="progressbar" aria-label="视频生成进度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><div id="progressBar"></div></div></div></section>
<div id="resultGrid" class="resultGrid"><div class="videoFrame"><video id="video" controls playsinline></video></div><section id="review"><h2 class="reviewTitle">字幕版本反馈</h2><div id="versionRow"><label class="fieldLabel" for="versions">视频版本</label><select id="versions"></select></div><label class="fieldLabel" for="reason">修改意见</label><textarea id="reason" maxlength="1000" placeholder="例如：标题太挤、正文层级不清楚"></textarea><div id="ratingButtons"><button type="button" class="positive" data-rating="positive">好看</button><button type="button" class="secondary" data-rating="negative">重新设计字幕</button></div><div id="feedbackMessage"></div></section></div>
<div class="pipeline" aria-label="生成流程"><span><b>01 正文</b>提取与中文化</span><span><b>02 素材</b>缩略图视觉筛选</span><span><b>03 编排</b>文案与时间线</span><span><b>04 渲染</b>竖屏 MP4</span></div>
</div></section></main><script>
const form=document.querySelector('#generate'),generateButton=document.querySelector('#generateButton'),urlInput=document.querySelector('#url'),statusCard=document.querySelector('#statusCard'),statusBadge=document.querySelector('#statusBadge'),statusEl=document.querySelector('#status'),progressWrap=document.querySelector('#progressWrap'),progressTrack=document.querySelector('#progressTrack'),progressBar=document.querySelector('#progressBar'),progressValue=document.querySelector('#progressValue'),versionPill=document.querySelector('#versionPill'),resultGrid=document.querySelector('#resultGrid'),video=document.querySelector('#video'),review=document.querySelector('#review'),versions=document.querySelector('#versions'),reason=document.querySelector('#reason'),feedbackMessage=document.querySelector('#feedbackMessage');
let currentJob=null,eventSource=null;
const stateLabels={queued:'排队中',running:'生成中',awaiting_browser_import:'等待导入',revising:'修订中',completed:'已完成',failed:'失败'};
function setVideo(src){if(!src)return;video.pause();video.src=src+'&cache='+Date.now();video.load();resultGrid.classList.add('ready')}
function renderProgress(job){const value=Math.max(0,Math.min(100,Number(job.progress)||0));statusCard.hidden=false;progressWrap.classList.toggle('failed',job.status==='failed');progressWrap.classList.toggle('paused',job.status==='awaiting_browser_import');progressBar.style.width=value+'%';progressValue.textContent=value+'%';progressTrack.setAttribute('aria-valuenow',String(value));progressTrack.setAttribute('aria-valuetext',(job.stage||job.status)+'，'+value+'%')}
function render(job){currentJob=job;const badgeClass=job.status==='awaiting_browser_import'?'paused':job.status;statusBadge.className='statusBadge '+badgeClass;statusBadge.textContent=stateLabels[job.status]||job.status;statusEl.textContent=job.stage||job.status;renderProgress(job);generateButton.disabled=['queued','running','revising'].includes(job.status);if(job.error)statusEl.textContent+='：'+job.error;if(job.status==='awaiting_browser_import'&&job.browser_import?.bookmarklet_url){statusEl.append(document.createTextNode(' · '));const a=document.createElement('a');a.href=job.browser_import.bookmarklet_url;a.textContent='导入当前文章';a.title='将此链接拖到书签栏，在文章页面点击';a.draggable=true;statusEl.append(a)}
const old=versions.value;versions.replaceChildren(...job.versions.map(v=>{const o=document.createElement('option');o.value=v.id;o.textContent=v.id+(v.id===job.current_version?'（当前）':'');o.dataset.url=v.video_url;return o}));versionPill.textContent=job.current_version?job.current_version+' · 1080×1920':'';if(job.versions.length){versions.value=job.versions.some(v=>v.id===old)?old:job.current_version;review.style.display='block';const selected=job.versions.find(v=>v.id===versions.value);if(selected&&video.dataset.version!==selected.id){video.dataset.version=selected.id;setVideo(selected.video_url)}}else{review.style.display='none';resultGrid.classList.remove('ready')}
document.querySelectorAll('[data-rating]').forEach(b=>b.disabled=job.status==='revising');if(job.feedback_status==='revising')feedbackMessage.textContent='正在生成新的字幕版本';else if(job.feedback_status==='completed')feedbackMessage.textContent='新字幕版本已生成';else if(job.feedback_status==='recorded')feedbackMessage.textContent='已记录偏好，将影响以后的视频';else if(job.feedback_status==='failed')feedbackMessage.textContent='修订失败：'+(job.error||'未知布局错误')+'；原视频仍然保留';}
function listen(id){eventSource?.close();eventSource=new EventSource('/api/jobs/'+id+'/events');eventSource.onmessage=e=>{const job=JSON.parse(e.data);render(job);if(job.status==='completed'||job.status==='failed')eventSource.close()};eventSource.onerror=()=>{if(currentJob&&!['completed','failed'].includes(currentJob.status)){statusEl.textContent='进度连接中断，正在重试'}}}
form.onsubmit=async e=>{e.preventDefault();eventSource?.close();video.pause();video.removeAttribute('src');video.load();resultGrid.classList.remove('ready');review.style.display='none';feedbackMessage.textContent='';generateButton.disabled=true;renderProgress({status:'queued',stage:'正在提交任务',progress:2});statusBadge.className='statusBadge running';statusBadge.textContent='提交中';statusEl.textContent='正在提交任务';try{const response=await fetch('/api/jobs',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({url:urlInput.value})});const job=await response.json();if(!response.ok){throw new Error(job.detail||'提交失败')}render(job);listen(job.id)}catch(error){render({status:'failed',stage:'提交失败',progress:2,error:error.message,versions:[]});generateButton.disabled=false}};
versions.onchange=()=>{const selected=currentJob?.versions.find(v=>v.id===versions.value);if(selected){video.dataset.version=selected.id;setVideo(selected.video_url)}};
document.querySelectorAll('[data-rating]').forEach(button=>button.onclick=async()=>{if(!currentJob)return;feedbackMessage.textContent='正在提交反馈';const response=await fetch('/api/jobs/'+currentJob.id+'/feedback',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({version_id:versions.value,rating:button.dataset.rating,reason:reason.value})});const job=await response.json();if(!response.ok){feedbackMessage.textContent=job.detail||'反馈提交失败';return}render(job);if(button.dataset.rating==='negative')listen(job.id);else reason.value=''})
</script></body></html>"""
