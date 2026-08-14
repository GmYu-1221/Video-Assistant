"""URL-to-reference-reel pipeline used by the local web application."""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from content_creator.schemas import AudioConfig, TimelineItem, VideoOutput, VideoProject
from content_creator.services.article import basic_asset_filter, capture_article_screenshots, chromium_available, discover_asset_candidates, download_selected_assets, fetch_article, log_asset_diagnostics, order_images, select_assets_with_agent, tag_images
from content_creator.services.assets import scan_and_process
from content_creator.services.music import analyze_audio, load_catalog, select_track
from content_creator.services.timeline import build_timeline
from content_creator.agents.render_agent import compile_render_plan

REFERENCE_WIDTH = 1080
REFERENCE_HEIGHT = 1920
REFERENCE_FPS = 30


def create_url_project(url: str, output_root: str | Path, on_progress=None) -> tuple[VideoProject, dict]:
    root = Path(output_root).resolve()
    project_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    project_dir = root / "projects" / project_id
    project_dir.mkdir(parents=True, exist_ok=False)
    diagnostics: dict = {"url": url}

    def persist_diagnostics() -> None:
        (project_dir / "asset_diagnostics.json").write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        log_asset_diagnostics(diagnostics)

    def persist_manifest(candidates, decisions) -> None:
        manifest = {
            "candidates": [item.model_dump(mode="json") for item in candidates],
            "decisions": [item.model_dump(mode="json") for item in decisions],
            "downloads": diagnostics.get("downloader", {}).get("items", []),
        }
        (project_dir / "asset_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    def progress(message: str) -> None:
        if on_progress:
            on_progress(message)

    progress("抓取文章")
    brief, soup = fetch_article(url)
    (project_dir / "article.json").write_text(brief.model_dump_json(indent=2), encoding="utf-8")
    progress("发现网页素材")
    candidates, discovery = discover_asset_candidates(soup, brief)
    diagnostics.update(discovery)
    progress("过滤网页素材")
    filtered = basic_asset_filter(candidates, diagnostics)
    progress("分析网页素材")
    decisions = select_assets_with_agent(brief, filtered, diagnostics)
    progress("下载已选素材")
    article_images = download_selected_assets(filtered, decisions, project_dir, diagnostics)
    persist_manifest(filtered, decisions)
    if len(article_images) < 4:
        diagnostics["screenshot_fallback"] = {"triggered": True, "reason": "selected_and_downloaded_images_below_minimum", "project_images_before_fallback": len(article_images), "missing": 4 - len(article_images)}
        persist_diagnostics()
        progress("准备正文截图引擎" if not chromium_available() else "补充正文截图")
        try:
            article_images.extend(capture_article_screenshots(brief.canonical_url, project_dir, len(article_images), 4 - len(article_images), diagnostics))
        except Exception as exc:
            diagnostics["screenshot_fallback"]["error"] = str(exc)
            persist_diagnostics()
            raise
    else:
        diagnostics["screenshot_fallback"] = {"triggered": False, "reason": "not_needed", "project_images_before_fallback": len(article_images), "missing": 0}
    progress("分析图片与生成文案")
    brief, copy, tags = tag_images(brief, article_images)
    selected, contexts = order_images(article_images, tags)
    if len(selected) < 4:
        raise ValueError("文章可用视觉素材少于 4 张")
    selected_dir = project_dir / "selected_images"
    selected_dir.mkdir()
    for index, image in enumerate(selected):
        shutil.copy2(image.local_path, selected_dir / f"{index:03d}.jpg")
    (project_dir / "article.json").write_text(brief.model_dump_json(indent=2), encoding="utf-8")
    (project_dir / "image_tags.json").write_text(json.dumps({"images": [image.model_dump(mode="json") for image in article_images], "tags": [tag.model_dump(mode="json") for tag in tags], "selected_ids": [image.id for image in selected], "transitions": [context.model_dump(mode="json") for context in contexts]}, ensure_ascii=False, indent=2), encoding="utf-8")
    progress("选择背景音乐")
    repo_root = Path(__file__).resolve().parents[3]
    track = select_track(load_catalog(repo_root), brief.mood, brief.topics)
    source_audio = repo_root / track.path
    if not source_audio.is_file():
        raise ValueError("曲库中没有可用的背景音乐")
    audio_dir = project_dir / "audio"
    audio_dir.mkdir()
    copied_audio = audio_dir / source_audio.name
    shutil.copy2(source_audio, copied_audio)
    assets = scan_and_process(selected_dir, project_dir, (1920, 1080))
    diagnostics["project_compile"] = {"project_images": len(assets), "relative_paths": [asset.relative_path for asset in assets], "source_asset_ids": [image.id for image in selected]}
    persist_diagnostics()
    analysis = analyze_audio(str(copied_audio))
    timeline = build_timeline(assets, analysis, REFERENCE_FPS, style="minimal")
    output = VideoOutput(project_dir=str(project_dir), render_data=str(project_dir / "render_data.json"), final_video=str(project_dir / "render" / "final.mp4"))
    project = VideoProject(project_id=project_id, fps=REFERENCE_FPS, width=REFERENCE_WIDTH, height=REFERENCE_HEIGHT, images=assets, audio=AudioConfig(path=f"audio/{copied_audio.name}", source_path=f"audio/{copied_audio.name}", duration=max(item.end_frame for item in timeline) / REFERENCE_FPS, sample_rate=analysis.sample_rate, bpm=analysis.bpm), timeline=timeline, output=output, video_copy=copy)
    progress("编排参考视频模板")
    # Deliberately omit the LLM VisualSpec decision: this template owns its effects.
    project = compile_render_plan(project, _storyboard_from_timeline(project), creative_plan=None)
    session_data = {"source": brief.model_dump(mode="json"), "music_track": track.model_dump(mode="json"), "transition_contexts": [item.model_dump(mode="json") for item in contexts], "project": project.model_dump(mode="json")}
    (project_dir / "session.json").write_text(json.dumps(session_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return project, session_data


def _storyboard_from_timeline(project: VideoProject):
    from content_creator.schemas import DirectorPlan, DirectorTimelineItem
    from content_creator.agents.director_agent import plan_to_storyboard
    return plan_to_storyboard(DirectorPlan(timeline=[DirectorTimelineItem(asset_id=item.asset_id, duration_frames=item.duration_frames, transition=item.transition, transition_strength=item.transition.intensity, reason="URL reference reel") for item in project.timeline]), "reference_reel")
