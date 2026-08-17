"""URL-to-reference-reel pipeline used by the local web application."""
from __future__ import annotations

import json
import math
import os
import random
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from content_creator.schemas import AudioConfig, BackgroundVideoConfig, BoundaryAction, CopyAction, ImageSemanticProfile, ImageTag, LayoutAction, LayoutPlan, TimelineItem, VideoCopy, VideoOutput, VideoProject
from content_creator.services.article import _brief_from_extraction, _is_verified_title_card, _title_match_score, augment_soup_with_selected_html, basic_asset_filter, capture_article_screenshots, chromium_available, classify_content_sufficiency, discover_asset_candidates, download_selected_assets, extract_article_html, fetch_article_with_extraction, log_asset_diagnostics, order_images, select_assets_with_agent, tag_images
from content_creator.services.assets import scan_and_process
from content_creator.services.music import analyze_audio, load_catalog, select_track
from content_creator.services.timeline import build_timeline
from content_creator.agents.render_agent import compile_render_plan
from content_creator.services.layout.validator import detect_layout_monotony, validate_persistent_title, validate_scene_layout
from content_creator.services.layout.qa import validate_rendered_layout, validate_rendered_persistent_title
from content_creator.services.layout.persistent_title import build_persistent_title_candidates, persistent_title_preflight_fits
from content_creator.agents.visual_critic import critique_scene
from content_creator.services.renderer.remotion import render_layout_still
from content_creator.services.timeline_state import default_url_actions, resolve_timeline
from content_creator.services.layout.preferences import TypographyPreferenceStore, article_context
from content_creator.services.article_localization import build_localized_video_copy, localize_article_copy, validate_localized_display_text
from content_creator.agents.viral_writer import create_viral_copy_plan, ordered_title_texts

REFERENCE_WIDTH = 1080
REFERENCE_HEIGHT = 1920
REFERENCE_FPS = 30
URL_SEGMENT_MIN_SECONDS = 2.5
URL_SEGMENT_MAX_SECONDS = 3.5
URL_COPY_CHARS_PER_SECOND = 8.0
URL_SEGMENT_BUFFER_SECONDS = 0.8
BACKGROUND_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm"}


def _asset_target_count(body_char_count: int) -> int:
    """Scale visual beats with article length; bounds are operator-configurable."""
    try:
        per_asset = max(100, int(os.getenv("URL_ASSET_CHARS_PER_IMAGE", "1200")))
    except ValueError:
        per_asset = 1200
    try:
        minimum = max(1, int(os.getenv("URL_ASSET_TARGET_MIN", "1")))
    except ValueError:
        minimum = 1
    try:
        maximum = max(minimum, int(os.getenv("URL_ASSET_TARGET_MAX", "8")))
    except ValueError:
        maximum = max(minimum, 8)
    return min(maximum, max(minimum, math.ceil(body_char_count / per_asset)))


def _select_background_video(source_dir: str | Path, project_dir: str | Path, *, rng=None) -> BackgroundVideoConfig:
    source_root = Path(source_dir).expanduser().resolve()
    if not source_root.is_dir():
        raise ValueError(f"背景视频目录不存在：{source_root}")
    candidates = sorted(path for path in source_root.iterdir() if path.is_file() and path.suffix.lower() in BACKGROUND_VIDEO_EXTENSIONS)
    mp4_candidates = [path for path in candidates if path.suffix.lower() == ".mp4"]
    candidates = mp4_candidates or candidates
    if not candidates:
        raise ValueError(f"背景视频目录中没有可用视频：{source_root}")
    selected = (rng or random.SystemRandom()).choice(candidates)
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-show_entries", "format=duration",
        "-of", "json", str(selected),
    ], check=False, capture_output=True, text=True)
    if probe.returncode:
        raise ValueError(f"无法读取背景视频：{selected.name}")
    try:
        payload = json.loads(probe.stdout)
        stream = payload["streams"][0]
        duration = float(payload["format"]["duration"])
        width, height = int(stream["width"]), int(stream["height"])
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"背景视频缺少有效视频流：{selected.name}") from exc
    target_dir = Path(project_dir) / "background"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"background{selected.suffix.lower()}"
    shutil.copy2(selected, target)
    return BackgroundVideoConfig(
        path=f"background/{target.name}", source_filename=selected.name,
        duration=duration, width=width, height=height,
    )


def _retime_resolved_bundle(bundle, profiles: dict, *, bpm: float, fps: int) -> list[dict]:
    """Fit URL segments to real rendered copy while preserving Director actions."""
    beat_seconds = 60.0 / max(bpm, 1.0)
    cursor = 0
    timing: list[dict] = []
    actions = []
    partial = []
    resolved = []
    for action, partial_item, state in zip(bundle.actions, bundle.partial, bundle.resolved):
        narrative = bundle.segment_narratives[state.segment_id]
        layout = bundle.segment_layouts[state.segment_id]
        contents = {item.content_id: item for item in narrative.contents}
        displayed = [contents[block.content_id].value(block.variant_id) for block in layout.text_blocks if block.content_id in contents]
        # Blocks are displayed concurrently. Use the longest reading burden,
        # rather than adding headline and explanation as if they were serial.
        visible_chars = max((len("".join(value.split())) for value in displayed), default=0)
        density = getattr(profiles.get(state.resolved_media_id), "information_density", .5) or .5
        dense_buffer = .25 if density >= .7 else 0.0
        requested_seconds = visible_chars / URL_COPY_CHARS_PER_SECOND + URL_SEGMENT_BUFFER_SECONDS + dense_buffer
        # Use the nearest musical beat, then clamp again. This keeps the fast
        # pace contract strict even when the beat period does not divide it.
        requested_seconds = max(URL_SEGMENT_MIN_SECONDS, min(URL_SEGMENT_MAX_SECONDS, requested_seconds))
        beat_aligned = round(requested_seconds / beat_seconds) * beat_seconds
        seconds = max(URL_SEGMENT_MIN_SECONDS, min(URL_SEGMENT_MAX_SECONDS, beat_aligned))
        frames = max(1, round(seconds * fps))
        transition = state.transition.model_copy(update={"duration_frames": min(state.transition.duration_frames, max(1, frames // 3))})
        end = cursor + frames
        actions.append(action.model_copy(update={"duration_frames": frames, "transition": transition}))
        partial.append(partial_item.model_copy(update={"duration_frames": frames, "transition": transition}))
        resolved.append(state.model_copy(update={"start_frame": cursor, "end_frame": end, "duration_frames": frames, "transition": transition}))
        timing.append({
            "segment_id": state.segment_id,
            "visible_character_count": visible_chars,
            "information_density": density,
            "requested_seconds": round(requested_seconds, 3),
            "actual_seconds": round(frames / fps, 3),
            "beat_seconds": round(beat_seconds, 3),
            "reading_speed_chars_per_second": URL_COPY_CHARS_PER_SECOND,
            "buffer_seconds": URL_SEGMENT_BUFFER_SECONDS,
        })
        cursor = end
    bundle.actions = actions
    bundle.partial = partial
    bundle.resolved = resolved
    return timing


def _select_persistent_title(title: str, font_palette: list[str] | None, remotion_public: Path, alternatives: list[str] | None = None):
    source_titles = []
    for value in [title, *(alternatives or [])]:
        if value and value not in source_titles:
            source_titles.append(value)
    sourced_candidates = [
        (source_title, candidate)
        for source_title in source_titles
        for candidate in build_persistent_title_candidates(source_title, font_palette)
    ]
    preflight = [(source_title, item, persistent_title_preflight_fits(item.content, item.font_id)) for source_title, item in sourced_candidates]
    candidates_to_audit = [(source_title, item) for source_title, item, passed in preflight if passed] or sourced_candidates
    attempts = []
    for source_title, candidate in candidates_to_audit:
        issues = validate_persistent_title(candidate)
        rendered = None if issues else validate_rendered_persistent_title(candidate, remotion_public)
        codes = [issue.code for issue in issues] + ([issue.code for issue in rendered.issues] if rendered else [])
        attempts.append({
            "source_title": source_title,
            "content": candidate.content,
            "preflight_passed": next(passed for source, item, passed in preflight if source == source_title and item.content_hash == candidate.content_hash),
            "issues": codes,
        })
        if not issues and rendered and rendered.passed:
            return candidate, rendered, attempts
    raise ValueError("顶部标题在三行区域内无法容纳")


def create_url_project(url: str, output_root: str | Path, on_progress=None, *, imported_html: str | None = None) -> tuple[VideoProject, dict]:
    def progress(message: str) -> None:
        if on_progress:
            on_progress(message)

    progress("抓取文章" if imported_html is None else "解析浏览器导入内容")
    if imported_html is None:
        extraction, soup = fetch_article_with_extraction(url)
    else:
        extraction, soup = extract_article_html(url, imported_html)
    brief = _brief_from_extraction(extraction)
    soup = augment_soup_with_selected_html(soup, extraction.selected_html)

    root = Path(output_root).resolve()
    project_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    project_dir = root / "projects" / project_id
    project_dir.mkdir(parents=True, exist_ok=False)
    sufficiency, sufficiency_metrics = classify_content_sufficiency(extraction.body, representation="text")
    if sufficiency == "invalid":
        raise ValueError("网页内容不是可用于视频的有效正文")
    diagnostics: dict = {"url": url, "browser_imported": imported_html is not None, "content_sufficiency": sufficiency_metrics, "article_extraction": extraction.diagnostics | {"requested_url": extraction.requested_url, "canonical_url": extraction.canonical_url, "effective_base_url": extraction.effective_base_url, "extraction_method": extraction.extraction_method, "extraction_confidence": extraction.extraction_confidence, "selected_candidate_ids": extraction.selected_candidate_ids, "final_body_chars": len(extraction.body)}}
    cleanup = extraction.diagnostics.get("html_cleanup", {})
    removed_ui = int(cleanup.get("ui_nodes_removed", 0)) + int(cleanup.get("structural_nodes_removed", 0))
    if removed_ui:
        progress(f"正文识别：已过滤 {removed_ui} 个页面 UI 节点，可用正文 {len(extraction.body)} 字")
    asset_target_count = _asset_target_count(len(brief.text))
    diagnostics["asset_target_count"] = asset_target_count

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

    source_brief = brief
    article_source = source_brief.model_dump(mode="json") | {
        "extraction_method": extraction.extraction_method,
        "selected_candidate_ids": extraction.selected_candidate_ids,
        "extraction_diagnostics": extraction.diagnostics,
    }
    (project_dir / "article_source.json").write_text(json.dumps(article_source, ensure_ascii=False, indent=2), encoding="utf-8")
    (project_dir / "article.json").write_text(brief.model_dump_json(indent=2), encoding="utf-8")
    progress("发现网页素材")
    candidates, discovery = discover_asset_candidates(soup, brief)
    diagnostics.update(discovery)
    progress("过滤网页素材")
    filtered = basic_asset_filter(candidates, diagnostics)
    progress("分析网页素材")
    decisions = select_assets_with_agent(brief, filtered, diagnostics, asset_target_count)
    progress("下载已选素材")
    article_images = download_selected_assets(filtered, decisions, project_dir, diagnostics, browser_imported=imported_html is not None, max_renderable=asset_target_count)
    persist_manifest(filtered, decisions)
    downloader = diagnostics.get("downloader", {})
    protected_assets = downloader.get("browser_asset_required", 0)
    summary = {
        "discovered": diagnostics.get("asset_discovery", {}).get("after_dedup", 0),
        "rule_filtered_remaining": diagnostics.get("rule_filter", {}).get("remaining", 0),
        "agent_preferred": diagnostics.get("asset_agent", {}).get("selected", 0),
        "downloaded": len(article_images),
        "candidate_pool_total": downloader.get("candidate_pool_total", 0),
        "candidate_pool_exhausted": downloader.get("candidate_pool_exhausted", False),
        "target_count": asset_target_count,
        "shortfall": max(0, asset_target_count - len(article_images)),
    }
    diagnostics["asset_summary"] = summary
    progress(f"素材状态：发现 {summary['discovered']} 个，优先选择 {summary['agent_preferred']} 个，成功下载 {summary['downloaded']} 个")
    if protected_assets:
        progress(f"已跳过 {protected_assets} 个浏览器受保护素材")
    if len(article_images) < asset_target_count and downloader.get("candidate_pool_exhausted"):
        diagnostics["screenshot_fallback"] = {"triggered": True, "reason": "selected_and_downloaded_images_below_dynamic_target", "project_images_before_fallback": len(article_images), "missing": asset_target_count - len(article_images), "target_count": asset_target_count}
        persist_diagnostics()
        progress("准备正文截图引擎" if not chromium_available() else "补充正文截图")
        try:
            screenshots = capture_article_screenshots(
                brief.effective_base_url or brief.url,
                project_dir,
                len(article_images),
                asset_target_count - len(article_images),
                diagnostics,
                selected_html=extraction.selected_html,
                body=extraction.body,
                title=extraction.title,
            )
            article_images.extend(screenshots)
            progress(f"正文截图：成功补充 {len(screenshots)} 张，当前素材 {len(article_images)} 张")
        except Exception as exc:
            diagnostics["screenshot_fallback"]["error"] = str(exc)
            persist_diagnostics()
            if not article_images:
                raise ValueError(f"正文有效，但没有可渲染画面；本地正文截图失败：{exc}") from exc
            diagnostics["screenshot_fallback"]["reduced_after_error"] = True
            progress(f"正文截图未补足，使用现有 {len(article_images)} 个素材缩短视频")
    elif len(article_images) < asset_target_count:
        diagnostics["screenshot_fallback"] = {"triggered": False, "reason": "download_pool_incomplete_using_available_assets", "project_images_before_fallback": len(article_images), "missing": asset_target_count - len(article_images)}
        if not article_images:
            raise ValueError("正文有效，但候选素材池没有产生可渲染画面")
    else:
        diagnostics["screenshot_fallback"] = {"triggered": False, "reason": "not_needed", "project_images_before_fallback": len(article_images), "missing": 0}
    progress("分析图片与生成文案")
    if imported_html is not None and protected_assets:
        # Browser import only supplied page HTML. Preserve the first Agent
        # decision set and avoid a second model call to compensate for assets
        # that the server is not authorized to download.
        candidates_by_id = {candidate.id: candidate for candidate in filtered}
        decisions_by_url = {
            candidates_by_id[decision.asset_id].source_url: decision
            for decision in decisions
            if decision.selected and decision.asset_id in candidates_by_id
        }
        tags = []
        for image in article_images:
            decision = decisions_by_url.get(image.source_url)
            if decision is None:
                tags.append(ImageTag(image_id=image.id, role="evidence", salience=.5, visual_quality=.6, section_index=image.source_index))
            else:
                tags.append(ImageTag(image_id=image.id, role=decision.role, topics=decision.topics, entities=decision.entities, salience=decision.relevance, visual_quality=decision.visual_quality, section_index=image.source_index))
        copy = VideoCopy(headline=brief.title[:80], subtitle=(brief.site_name or "文章要点")[:40], body=brief.text[:400])
        brief = brief.model_copy(update={"summary": brief.text[:1200], "topics": [topic for tag in tags for topic in tag.topics][:12]})
        diagnostics.setdefault("asset_agent", {})["tagging_skipped_due_browser_assets"] = True
    else:
        brief, copy, tags = tag_images(brief, article_images)
    progress("翻译中文说明文案")
    brief, localized_copy, localization_diagnostics = localize_article_copy(brief)
    copy = build_localized_video_copy(brief, localized_copy, preferred=copy)
    progress("Viral Writer 正在策划标题和正文")
    viral_copy_plan, viral_copy_diagnostics = create_viral_copy_plan(brief, tags, asset_target_count)
    viral_title_options = ordered_title_texts(viral_copy_plan)
    brief = brief.model_copy(update={"title": viral_copy_plan.final_title})
    localized_copy = localized_copy.model_copy(update={"title": viral_copy_plan.final_title})
    copy = copy.model_copy(update={"headline": viral_copy_plan.final_title[:80]})
    diagnostics["viral_writer"] = viral_copy_diagnostics | {
        "selected_title_id": viral_copy_plan.selected_title_id,
        "selected_title": viral_copy_plan.final_title,
        "title_candidate_count": len(viral_copy_plan.title_candidates),
        "content_unit_count": len(viral_copy_plan.content_units),
    }
    (project_dir / "viral_copy_plan.json").write_text(viral_copy_plan.model_dump_json(indent=2), encoding="utf-8")
    localized_hashes = [sha256(paragraph.encode("utf-8")).hexdigest() for paragraph in localized_copy.paragraphs]
    diagnostics["localized_copy"] = localization_diagnostics | {
        "localized_paragraph_hashes": localized_hashes,
        "summary_source_paragraph_indices": localized_copy.source_paragraph_indices,
        "article_body_source_hash": sha256(extraction.body.encode("utf-8")).hexdigest(),
    }
    (project_dir / "localized_copy.json").write_text(localized_copy.model_dump_json(indent=2), encoding="utf-8")
    selected, contexts = order_images(article_images, tags, title=brief.title, target_count=asset_target_count)
    if not selected:
        raise ValueError("正文有效，但没有可用于视频的视觉素材")
    diagnostics["asset_summary"].update({
        "actual_count": len(selected),
        "shortened": len(selected) < asset_target_count,
        "reduction_reason": "available_nonduplicate_assets_below_target" if len(selected) < asset_target_count else None,
    })
    tag_by_id = {tag.image_id: tag for tag in tags}
    opening_tag = tag_by_id.get(selected[0].id)
    opening_has_verified_headline = _is_verified_title_card(selected[0], opening_tag)
    opening_reason = "verified_prominent_headline_title_match" if opening_has_verified_headline else "prominent_headline_unavailable"
    diagnostics["selected_asset_order"] = [{
        "image_id": image.id,
        "source_url": image.source_url,
        "title_match_score": _title_match_score(brief.title, image, tag_by_id.get(image.id)),
        "role": tag_by_id.get(image.id).role.value if tag_by_id.get(image.id) else "other",
        "contains_prominent_headline": tag_by_id.get(image.id).contains_prominent_headline if tag_by_id.get(image.id) else None,
        "embedded_headline_text": tag_by_id.get(image.id).embedded_headline_text if tag_by_id.get(image.id) else "",
        "headline_prominence": tag_by_id.get(image.id).headline_prominence if tag_by_id.get(image.id) else 0,
        "headline_title_match_score": tag_by_id.get(image.id).headline_title_match_score if tag_by_id.get(image.id) else 0,
        "headline_readability": tag_by_id.get(image.id).headline_readability if tag_by_id.get(image.id) else 0,
        "headline_analysis_status": tag_by_id.get(image.id).headline_analysis_status if tag_by_id.get(image.id) else "unavailable",
        "opening_selection_reason": opening_reason if image.id == selected[0].id else "",
    } for image in selected]
    diagnostics["opening_image"] = {
        "image_id": selected[0].id,
        "reason": opening_reason,
        "embedded_headline_text": opening_tag.embedded_headline_text if opening_tag else "",
        "headline_analysis_status": opening_tag.headline_analysis_status if opening_tag else "unavailable",
    }
    diagnostics["scene_count"] = len(selected)
    selected_dir = project_dir / "selected_images"
    selected_dir.mkdir()
    for index, image in enumerate(selected):
        shutil.copy2(image.local_path, selected_dir / f"{index:03d}.jpg")
    (project_dir / "article.json").write_text(brief.model_dump_json(indent=2), encoding="utf-8")
    title_match_scores = {image.id: _title_match_score(brief.title, image, tag_by_id.get(image.id)) for image in selected}
    (project_dir / "image_tags.json").write_text(json.dumps({"images": [image.model_dump(mode="json") for image in article_images], "tags": [tag.model_dump(mode="json") for tag in tags], "selected_ids": [image.id for image in selected], "selected_asset_order": [image.id for image in selected], "title_match_scores": title_match_scores, "opening_image_reason": opening_reason, "opening_image_id": selected[0].id, "transitions": [context.model_dump(mode="json") for context in contexts]}, ensure_ascii=False, indent=2), encoding="utf-8")
    progress("选择背景音乐")
    repo_root = Path(__file__).resolve().parents[3]
    music_dir = os.getenv("URL_MUSIC_DIR", str(repo_root / "input" / "music"))
    music_catalog = load_catalog(repo_root, music_dir)
    track = select_track(music_catalog, brief.mood, brief.topics)
    source_audio = repo_root / track.path
    if not source_audio.is_file():
        raise ValueError("曲库中没有可用的背景音乐")
    diagnostics["background_music"] = {
        "library_dir": str(Path(music_dir).expanduser().resolve()),
        "candidate_count": len(music_catalog),
        "selected_track_id": track.id,
        "selected_source": str(source_audio.resolve()),
        "selection_mode": "mood_topic_energy",
    }
    audio_dir = project_dir / "audio"
    audio_dir.mkdir()
    copied_audio = audio_dir / source_audio.name
    shutil.copy2(source_audio, copied_audio)
    progress("选择随机背景视频")
    background_dir = os.getenv("URL_BACKGROUND_VIDEO_DIR", str(repo_root / "input" / "bgv"))
    background_video = _select_background_video(background_dir, project_dir)
    diagnostics["background_video"] = background_video.model_dump(mode="json") | {
        "selection_mode": "random_once_per_project",
        "main_timeline_unchanged": True,
        "duration_behavior": "loop_if_short_trim_if_long",
    }
    assets = scan_and_process(selected_dir, project_dir, (1920, 1080))
    selected_by_index = {index: image for index, image in enumerate(selected)}
    tag_by_id = {tag.image_id: tag for tag in tags}
    enriched_assets = []
    for index, asset in enumerate(assets):
        source = selected_by_index.get(index)
        tag = tag_by_id.get(source.id) if source else None
        profile = ImageSemanticProfile(
            role=tag.role.value if tag else "other",
            narrative_function="evidence" if tag and tag.role.value in {"evidence", "data", "diagram"} else "context",
            contains_text=True if tag and tag.contains_prominent_headline else None,
            is_screenshot=bool(source and source.source_url.startswith("screenshot://")),
            is_data_chart=tag.role.value in {"data", "diagram"} if tag else None,
            importance=tag.salience if tag else .5,
            information_density=.75 if tag and tag.role.value in {"data", "diagram"} else .35,
            source_caption=source.caption if source else "",
            generated_description=source.alt if source else "",
            contains_prominent_headline=tag.contains_prominent_headline if tag else None,
            embedded_headline_text=tag.embedded_headline_text if tag else "",
            headline_prominence=tag.headline_prominence if tag else 0,
            headline_title_match_score=tag.headline_title_match_score if tag else 0,
            headline_bbox=tag.headline_bbox if tag else None,
            headline_readability=tag.headline_readability if tag else 0,
            headline_analysis_status=tag.headline_analysis_status if tag else "unavailable",
            headline_exclusion_reason=tag.headline_exclusion_reason if tag else "",
        )
        enriched_assets.append(asset.model_copy(update={"semantic_profile": profile}))
    assets = enriched_assets
    diagnostics["project_compile"] = {"project_images": len(assets), "relative_paths": [asset.relative_path for asset in assets], "source_asset_ids": [image.id for image in selected], "scene_count": len(selected)}
    persist_diagnostics()
    analysis = analyze_audio(str(copied_audio))
    timeline = build_timeline(assets, analysis, REFERENCE_FPS, style="minimal")
    output = VideoOutput(project_dir=str(project_dir), render_data=str(project_dir / "render_data.json"), final_video=str(project_dir / "render" / "final.mp4"))
    progress("Director 编排连续性状态")
    actions = default_url_actions(timeline, assets)
    profiles = {asset.id: asset.semantic_profile for asset in assets}
    preference_summary = TypographyPreferenceStore(root).summary_for(brief)
    layout_context = article_context(brief)
    layout_context["pace"] = "fast"
    layout_context["target_segment_count"] = asset_target_count
    layout_context["segment_duration_range_seconds"] = [URL_SEGMENT_MIN_SECONDS, URL_SEGMENT_MAX_SECONDS]
    if sufficiency == "compact" or len(assets) == 1:
        layout_context["copy_density_intent"] = "reduce"
    bundle = resolve_timeline(actions, profiles, title=brief.title, body=brief.text, summary=brief.summary, layout_context=layout_context, layout_preferences=preference_summary, copy_plan=viral_copy_plan)
    timing_diagnostics = _retime_resolved_bundle(bundle, profiles, bpm=analysis.bpm, fps=REFERENCE_FPS)
    actions = bundle.actions
    actual_duration = sum(item.duration_frames for item in bundle.resolved) / REFERENCE_FPS
    diagnostics["video_scope"] = {
        "content_classification": sufficiency,
        "semantic_unit_count": len({content.semantic_unit_id for narrative in bundle.narratives.values() for content in narrative.contents}),
        "uncompressed_target_count": math.ceil(len(brief.text) / 650) if brief.text else 1,
        "desired_asset_count": asset_target_count,
        "actual_asset_count": len(assets),
        "final_segment_count": len(bundle.resolved),
        "target_duration_seconds": round(actual_duration, 3),
        "actual_duration_seconds": round(actual_duration, 3),
        "shortened": len(assets) < asset_target_count or sufficiency == "compact",
        "compression_reason": "fast_pace_core_points" if len(brief.text) > 0 else "no_body_text",
        "reading_speed_chars_per_second": URL_COPY_CHARS_PER_SECOND,
        "segment_duration_range_seconds": [URL_SEGMENT_MIN_SECONDS, URL_SEGMENT_MAX_SECONDS],
        "omitted_semantic_unit_count": max(0, len(viral_copy_plan.content_units) - len({content.semantic_unit_id for narrative in bundle.narratives.values() for content in narrative.contents})),
        "reduction_reasons": [reason for reason in ["compact_article" if sufficiency == "compact" else None, "limited_visual_assets" if len(assets) < asset_target_count else None] if reason],
        "segments": timing_diagnostics,
    }
    progress(f"已提炼为 {len(bundle.resolved)} 个镜头、预计 {actual_duration:.1f} 秒")
    persistent_title, persistent_title_rendered, title_attempts = _select_persistent_title(
        brief.title,
        bundle.layout_diagnostics.get("font_palette"),
        repo_root / "remotion" / "public",
        alternatives=viral_title_options[1:],
    )
    selected_source_title = next((attempt["source_title"] for attempt in reversed(title_attempts) if not attempt["issues"]), viral_copy_plan.final_title)
    selected_candidate = next((item for item in viral_copy_plan.title_candidates if item.text == selected_source_title), viral_copy_plan.selected_title)
    viral_copy_plan = viral_copy_plan.model_copy(update={"selected_title_id": selected_candidate.candidate_id, "final_title": persistent_title.content})
    brief = brief.model_copy(update={"title": persistent_title.content})
    localized_copy = localized_copy.model_copy(update={"title": persistent_title.content})
    copy = copy.model_copy(update={"headline": persistent_title.content[:80]})
    diagnostics["viral_writer"].update({"selected_title_id": viral_copy_plan.selected_title_id, "selected_title": persistent_title.content, "persistent_title_attempts": title_attempts})
    (project_dir / "viral_copy_plan.json").write_text(viral_copy_plan.model_dump_json(indent=2), encoding="utf-8")
    (project_dir / "localized_copy.json").write_text(localized_copy.model_dump_json(indent=2), encoding="utf-8")
    (project_dir / "article.json").write_text(brief.model_dump_json(indent=2), encoding="utf-8")
    bundle.layout_diagnostics["persistent_title_candidates"] = title_attempts
    missing_state = [state.segment_id for state in bundle.resolved if not state.resolved_layout_id or not state.resolved_copy_id]
    if missing_state:
        raise ValueError(f"URL 布局状态不完整，无法安全渲染：{', '.join(missing_state)}")
    (project_dir / "scene_narrative_plan.json").write_text(json.dumps({"persistent_title": persistent_title.model_dump(mode="json"), "narratives": [item.model_dump(mode="json") for item in bundle.narratives.values()]}, ensure_ascii=False, indent=2), encoding="utf-8")
    layout_plan = LayoutPlan(global_style="editorial", persistent_title=persistent_title, scenes=list(bundle.layouts.values()))
    (project_dir / "layout_plan.json").write_text(layout_plan.model_dump_json(indent=2), encoding="utf-8")
    qa = {"layout_director": bundle.layout_diagnostics, "preference_memory": preference_summary, "persistent_title": {"spec": persistent_title.model_dump(mode="json"), "hard_issues": [], "rendered": persistent_title_rendered.model_dump(mode="json")}, "invalidation_matrix": {"all_hold": "none", "media_replace": ["geometry", "crop", "subject", "contrast"], "copy_replace_or_hide": ["typography", "wrapping", "overflow", "contrast", "visibility"], "layout_adapt": ["changed_blocks", "collision"], "layout_replace": ["full_chromium_audit", "visual_critic"]}, "segments": []}
    updated_timeline = []
    for action, state in zip(actions, bundle.resolved):
        narrative = bundle.segment_narratives[state.segment_id]
        layout = bundle.segment_layouts[state.segment_id]
        profile = profiles[state.resolved_media_id]
        all_hold = action.media_action.value == "hold" and action.copy_action.value == "hold" and action.layout_action.value == "hold"
        scopes = []
        if action.media_action.value == "replace": scopes += ["geometry", "crop", "subject", "contrast"]
        if action.copy_action in {CopyAction.replace, CopyAction.hide}: scopes += ["typography", "wrapping", "overflow", "contrast", "visibility"]
        if state.resolved_layout_action == LayoutAction.adapt: scopes += ["changed_blocks", "collision"]
        if state.resolved_layout_action == LayoutAction.replace: scopes = ["full_chromium_audit", "visual_critic"]
        issues = [] if all_hold else validate_scene_layout(layout, narrative, profile)
        rendered = None if all_hold or issues else validate_rendered_layout(layout, narrative, repo_root / "remotion" / "public")
        qa["segments"].append({"segment_id": state.segment_id, "scene_id": state.scene_id, "qa_scope": sorted(set(scopes)), "reused_previous_qa": all_hold, "hard_issues": [issue.model_dump() for issue in issues], "rendered": rendered.model_dump(mode="json") if rendered else None, "requested_layout_action": state.requested_layout_action.value, "resolved_layout_action": state.resolved_layout_action.value, "override_reason": state.override_reason})
        updated_timeline.append(TimelineItem(asset_id=state.resolved_media_id, start_frame=state.start_frame, end_frame=state.end_frame, duration_frames=state.duration_frames, transition=state.transition, narrative=narrative, layout=layout, resolved_state=state))
    independent = []
    seen_layouts = set()
    for state in bundle.resolved:
        layout = bundle.segment_layouts[state.segment_id]
        if layout.layout_id in seen_layouts:
            continue
        seen_layouts.add(layout.layout_id)
        narrative = bundle.segment_narratives[state.segment_id]
        independent.append((layout, narrative.scene_purpose, profiles[state.resolved_media_id]))
    qa["layout_monotony"] = [issue.model_dump(mode="json") for issue in detect_layout_monotony(independent)]
    (project_dir / "director_timeline.json").write_text(json.dumps({"actions": [item.model_dump(mode="json") for item in actions], "partial_state": [item.model_dump(mode="json") for item in bundle.partial], "resolved_state": [item.model_dump(mode="json") for item in bundle.resolved], "safety_overrides": bundle.audit}, ensure_ascii=False, indent=2), encoding="utf-8")
    (project_dir / "layout_qa.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")
    final_texts = []
    text_block_count = 0
    scenes_with_multiple_text_blocks = 0
    repeated_copy_groups: dict[str, list[str]] = {}
    for item in updated_timeline:
        if item.narrative is None or item.layout is None or item.resolved_state is None:
            raise ValueError(f"URL timeline item 缺少 narrative/layout/resolved_state：{item.asset_id}")
        content_by_id = {content.content_id: content for content in item.narrative.contents}
        scene_texts = []
        for block in item.layout.text_blocks:
            content = content_by_id.get(block.content_id)
            if content is None:
                raise ValueError(f"布局引用未知文案：{block.content_id}")
            value = content.value(block.variant_id)
            final_texts.append(value)
            scene_texts.append(value)
            text_block_count += 1
            repeated_copy_groups.setdefault(content.source_hash, []).append(item.resolved_state.segment_id)
        if len(set(scene_texts)) >= 2:
            scenes_with_multiple_text_blocks += 1
    display_issues = validate_localized_display_text(final_texts)
    if display_issues:
        raise ValueError("中文文案校验失败：" + "; ".join(display_issues[:8]))
    duplicate_groups = {key: sorted(set(value)) for key, value in repeated_copy_groups.items() if len(set(value)) > 1}
    diagnostics["localized_display"] = {
        "localized_text_block_count": text_block_count,
        "localized_text_character_count": sum(len(value) for value in final_texts),
        "english_explanatory_block_count": 0,
        "scene_count": len(updated_timeline),
        "scenes_with_multiple_text_blocks": scenes_with_multiple_text_blocks,
        "repeated_copy_groups": duplicate_groups,
        "video_copy_source": "viral_writer" if diagnostics.get("viral_writer", {}).get("mode") == "model_success" else "localized_copy_fallback",
        "render_path": "url_layout_renderer",
    }
    persist_diagnostics()
    project = VideoProject(project_id=project_id, fps=REFERENCE_FPS, width=REFERENCE_WIDTH, height=REFERENCE_HEIGHT, images=assets, audio=AudioConfig(path=f"audio/{copied_audio.name}", source_path=f"audio/{copied_audio.name}", duration=actual_duration, sample_rate=analysis.sample_rate, bpm=analysis.bpm), background_video=background_video, timeline=updated_timeline, output=output, video_copy=copy, persistent_title=persistent_title)
    progress("编排动态布局视频")
    project = compile_render_plan(project, _storyboard_from_timeline(project), creative_plan=None)
    # Rendered previews are durable QA evidence and are generated with the
    # exact same composition, bundled fonts, and media URL strategy as final.
    # Render all Chromium stills first, then critique scenes concurrently. A
    # serial preview -> network critic loop makes a long article look frozen
    # at 85% and multiplies model latency by the number of scenes.
    previews_root = project_dir / "layout" / "previews"
    preview_jobs: list[tuple[int, TimelineItem, dict]] = []
    for index, item in enumerate(project.timeline):
        scene_record = qa["segments"][index]
        scene_dir = previews_root / item.resolved_state.segment_id
        preview_paths = []
        frames = {"settled": min(item.end_frame - 1, item.start_frame + 12), "middle": item.start_frame + item.duration_frames // 2}
        if any(block.typography_role.value == "caption" for block in item.layout.text_blocks):
            frames["caption"] = min(item.end_frame - 1, item.start_frame + max(12, item.duration_frames // 3))
        progress(f"布局预览：{index + 1}/{len(project.timeline)} 个镜头")
        try:
            for label, frame in frames.items():
                path = render_layout_still(project, repo_root / "remotion", scene_dir / f"{label}.png", frame)
                preview_paths.append(str(path))
                audit_path = path.with_suffix(".audit.json")
                if audit_path.is_file():
                    scene_record.setdefault("remotion_dom_audits", []).append(json.loads(audit_path.read_text(encoding="utf-8")))
            scene_record["preview_paths"] = preview_paths
        except Exception as exc:
            scene_record["preview_error"] = str(exc)
        preview_jobs.append((index, item, scene_record))

    try:
        concurrency = max(1, min(4, int(os.getenv("URL_VISUAL_CRITIC_CONCURRENCY", "3"))))
    except ValueError:
        concurrency = 3

    def run_critic(job):
        index, item, scene_record = job
        rendered = scene_record.get("rendered") or {}
        return index, critique_scene(
            rendered_ok=bool(rendered.get("passed")),
            hard_issues=[],
            preview_paths=scene_record.get("preview_paths", []),
            scene_purpose=item.narrative.scene_purpose,
        )

    progress(f"视觉检查：0/{len(preview_jobs)} 个镜头（并发 {concurrency}）")
    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="layout-critic") as critic_pool:
        futures = [critic_pool.submit(run_critic, job) for job in preview_jobs]
        completed_critics = 0
        for future in as_completed(futures):
            index, critic = future.result()
            qa["segments"][index]["visual_critic"] = critic.model_dump(mode="json")
            completed_critics += 1
            progress(f"视觉检查：{completed_critics}/{len(futures)} 个镜头")
    (project_dir / "layout_qa.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")
    session_data = {"source": brief.model_dump(mode="json"), "music_track": track.model_dump(mode="json"), "transition_contexts": [item.model_dump(mode="json") for item in contexts], "project": project.model_dump(mode="json")}
    (project_dir / "session.json").write_text(json.dumps(session_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return project, session_data


def _storyboard_from_timeline(project: VideoProject):
    from content_creator.schemas import DirectorPlan, DirectorTimelineItem
    from content_creator.agents.director_agent import plan_to_storyboard
    return plan_to_storyboard(DirectorPlan(timeline=[DirectorTimelineItem(asset_id=item.asset_id, duration_frames=item.duration_frames, transition=item.transition, transition_strength=item.transition.intensity, reason="URL reference reel") for item in project.timeline]), "reference_reel")
