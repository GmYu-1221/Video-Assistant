import json
from pathlib import Path

from pydantic import ValidationError

from content_creator.schemas import NarrativeContent
from content_creator.web import FeedbackRequest, Job, JobManager, JobVersion, _PAGE, _job_payload, _public_error_message, create_app


def test_web_app_exposes_single_url_job_api(tmp_path):
    app = create_app(tmp_path)
    routes = {route.path for route in app.routes}
    assert "/api/jobs" in routes
    assert "/api/jobs/{job_id}" in routes
    assert "/api/jobs/{job_id}/events" in routes
    assert "/api/jobs/{job_id}/video" in routes
    assert "/api/jobs/{job_id}/feedback" in routes
    assert "/api/browser-import" in routes
    assert "/api/browser-asset-upload" in routes


def test_web_page_contains_accessible_stage_progress_bar():
    assert 'role="progressbar"' in _PAGE
    assert 'aria-valuenow="0"' in _PAGE
    assert "renderProgress(job)" in _PAGE


def test_job_progress_is_monotonic_and_completes_with_job_status():
    job = Job(id="job-progress", url="https://example.com/article", status="running")
    job.event("抓取文章")
    assert job.progress == 8
    job.event("下载已选素材")
    assert job.progress == 42
    job.event("正文识别：迟到的旧阶段事件")
    assert job.progress == 42
    job.status = "failed"
    job.event("生成失败")
    assert job.progress == 42
    assert _job_payload(job)["progress"] == 42
    job.status = "completed"
    job.event("已完成")
    assert job.progress == 100
    assert job.events[-1]["progress"] == 100


def test_public_validation_error_does_not_expose_input_or_pydantic_url():
    try:
        NarrativeContent(semantic_unit_id="unit", content_id="copy", full="正文", short="短文", micro="x" * 181)
    except ValidationError as exc:
        message = _public_error_message(exc)
    assert "micro" in message
    assert "input_value" not in message
    assert "pydantic.dev" not in message


def test_browser_import_waiting_payload_and_resume(tmp_path, monkeypatch):
    manager = JobManager(tmp_path, Path.cwd())
    job = Job(id="job-1", url="https://zhuanlan.zhihu.com/p/1", status="awaiting_browser_import", browser_import_status=403, browser_import_url=manager.browser_import_url())
    with manager.lock:
        manager.jobs[job.id] = job
    payload = _job_payload(job)
    assert payload["browser_import"]["status_code"] == 403
    assert payload["browser_import"]["bookmarklet_url"].startswith("javascript:")
    monkeypatch.setattr(manager, "_run", lambda *_args, **_kwargs: None)
    resumed = manager.accept_browser_import(manager.import_token, "https://zhuanlan.zhihu.com/p/1#section", "<article><p>imported</p></article>")
    assert resumed is job
    assert job.status == "running"


def test_positive_feedback_is_persisted_without_rendering(tmp_path):
    from content_creator.schemas import AudioConfig, ImageAsset, TimelineItem, VideoCopy, VideoOutput, VideoProject
    from content_creator.services.layout.fallback import solve_scene
    from content_creator.services.layout.revision import write_version_snapshot
    from content_creator.schemas import ImageSemanticProfile, NarrativeContent, SceneNarrative, ResolvedTimelineItem, BoundaryAction, LayoutAction, TransitionConfig

    manager = JobManager(tmp_path, Path.cwd())
    project_dir = tmp_path / "projects" / "project-1"
    project_dir.mkdir(parents=True)
    brief = {"url": "https://example.com/a", "requested_url": "https://example.com/a", "canonical_url": "https://example.com/a", "effective_base_url": "https://example.com/a", "title": "测试文章", "text": "测试正文足够长", "summary": "测试", "topics": ["technology"], "mood": "modern"}
    (project_dir / "article.json").write_text(json.dumps(brief), encoding="utf-8")
    image_path = project_dir / "image.jpg"
    image_path.write_bytes(b"x")
    content = NarrativeContent(semantic_unit_id="unit", content_id="primary", full="测试标题内容", short="测试标题", micro="测试")
    narrative = SceneNarrative(copy_id="copy", scene_id="scene", asset_id="image", scene_purpose="opening", contents=[content])
    layout = solve_scene(narrative, ImageSemanticProfile())
    state = ResolvedTimelineItem(segment_id="segment-0", scene_id="scene", start_frame=0, end_frame=30, duration_frames=30, resolved_media_id="image", resolved_copy_id="copy", resolved_layout_id=layout.layout_id, visibility="visible", boundary_action=BoundaryAction.continuous, requested_layout_action=LayoutAction.replace, resolved_layout_action=LayoutAction.replace, transition=TransitionConfig())
    project = VideoProject(project_id="project-1", fps=30, width=1080, height=1920, images=[ImageAsset(id="image", filename="image.jpg", relative_path="image.jpg", width=1080, height=610, semantic_profile=ImageSemanticProfile())], audio=AudioConfig(path="audio.wav", duration=1, sample_rate=44100), timeline=[TimelineItem(asset_id="image", start_frame=0, end_frame=30, duration_frames=30, transition=TransitionConfig(), narrative=narrative, layout=layout, resolved_state=state)], output=VideoOutput(project_dir=str(project_dir), render_data=str(project_dir / "render_data.json"), final_video=str(project_dir / "render" / "final.mp4")), video_copy=VideoCopy())
    version_dir = project_dir / "versions" / "v001"
    write_version_snapshot(project, version_dir, source_project_dir=project_dir)
    video = version_dir / "final.mp4"
    video.write_bytes(b"placeholder")
    job = manager._attach(Job(id="job-feedback", url=brief["url"], status="completed", project_dir=str(project_dir), versions=[JobVersion(id="v001", video_path=str(video), project_path=str(version_dir / "project.json"), created_at="now")], current_version="v001", video_path=str(video)))
    manager.jobs[job.id] = job
    result = manager.submit_feedback(job.id, FeedbackRequest(version_id="v001", rating="positive", reason="标题很舒服"))
    assert result.status == "completed"
    assert result.feedback_status == "recorded"
    stored = json.loads((tmp_path / "preferences" / "typography_feedback.jsonl").read_text(encoding="utf-8").strip())
    assert stored["rating"] == "positive"
    assert stored["reason"] == "标题很舒服"
