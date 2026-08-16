"""URL-to-reference-reel pipeline used by the local web application."""
from __future__ import annotations

import json
import math
import os
import shutil
from datetime import datetime
from pathlib import Path

from content_creator.schemas import AudioConfig, BoundaryAction, CopyAction, ImageSemanticProfile, ImageTag, LayoutAction, LayoutPlan, TimelineItem, VideoCopy, VideoOutput, VideoProject
from content_creator.services.article import _brief_from_extraction, _title_match_score, augment_soup_with_selected_html, basic_asset_filter, capture_article_screenshots, chromium_available, discover_asset_candidates, download_selected_assets, extract_article_html, fetch_article_with_extraction, log_asset_diagnostics, order_images, select_assets_with_agent, tag_images
from content_creator.services.assets import scan_and_process
from content_creator.services.music import analyze_audio, load_catalog, select_track
from content_creator.services.timeline import build_timeline
from content_creator.agents.render_agent import compile_render_plan
from content_creator.services.layout.validator import detect_layout_monotony, validate_scene_layout
from content_creator.services.layout.qa import validate_rendered_layout
from content_creator.agents.visual_critic import critique_scene
from content_creator.services.renderer.remotion import render_layout_still
from content_creator.services.timeline_state import default_url_actions, resolve_timeline
from content_creator.services.layout.preferences import TypographyPreferenceStore, article_context
from content_creator.services.article_localization import build_localized_video_copy, localize_article_copy, validate_localized_display_text

REFERENCE_WIDTH = 1080
REFERENCE_HEIGHT = 1920
REFERENCE_FPS = 30


def _asset_target_count(body_char_count: int) -> int:
    """Scale visual beats with article length; bounds are operator-configurable."""
    try:
        per_asset = max(100, int(os.getenv("URL_ASSET_CHARS_PER_IMAGE", "650")))
    except ValueError:
        per_asset = 650
    try:
        minimum = max(1, int(os.getenv("URL_ASSET_TARGET_MIN", "4")))
    except ValueError:
        minimum = 4
    try:
        maximum = max(minimum, int(os.getenv("URL_ASSET_TARGET_MAX", "12")))
    except ValueError:
        maximum = max(minimum, 12)
    return min(maximum, max(minimum, math.ceil(body_char_count / per_asset)))


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
    diagnostics: dict = {"url": url, "browser_imported": imported_html is not None, "article_extraction": extraction.diagnostics | {"requested_url": extraction.requested_url, "canonical_url": extraction.canonical_url, "effective_base_url": extraction.effective_base_url, "extraction_method": extraction.extraction_method, "extraction_confidence": extraction.extraction_confidence, "selected_candidate_ids": extraction.selected_candidate_ids, "final_body_chars": len(extraction.body)}}
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
            screenshot_count = asset_target_count - len(article_images)
            article_images.extend(capture_article_screenshots(
                brief.effective_base_url or brief.url,
                project_dir,
                len(article_images),
                asset_target_count - len(article_images),
                diagnostics,
                selected_html=extraction.selected_html,
                body=extraction.body,
                title=extraction.title,
            ))
            progress(f"正文截图：成功补充 {screenshot_count} 张，当前素材 {len(article_images)} 张")
        except Exception as exc:
            diagnostics["screenshot_fallback"]["error"] = str(exc)
            persist_diagnostics()
            details = f"发现 {summary['discovered']} 个候选、优先选择 {summary['agent_preferred']} 个、成功下载 {len(article_images)} 个"
            raise ValueError(f"{details}；正文截图兜底失败：{exc}") from exc
    elif len(article_images) < asset_target_count:
        # This is intentionally a hard invariant. A screenshot must never hide
        # a candidate-pool truncation or an interrupted downloader.
        raise ValueError("候选素材池尚未耗尽，不能执行正文截图兜底")
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
    diagnostics["localized_copy"] = localization_diagnostics
    (project_dir / "localized_copy.json").write_text(localized_copy.model_dump_json(indent=2), encoding="utf-8")
    selected, contexts = order_images(article_images, tags, title=brief.title, target_count=asset_target_count)
    if len(selected) < min(4, asset_target_count):
        raise ValueError(f"文章可用视觉素材少于最低要求：{len(selected)}/{min(4, asset_target_count)}")
    tag_by_id = {tag.image_id: tag for tag in tags}
    diagnostics["selected_asset_order"] = [{"image_id": image.id, "source_url": image.source_url, "title_match_score": _title_match_score(source_brief.title, image, tag_by_id.get(image.id)), "role": tag_by_id.get(image.id).role.value if tag_by_id.get(image.id) else "other"} for image in selected]
    diagnostics["scene_count"] = len(selected)
    selected_dir = project_dir / "selected_images"
    selected_dir.mkdir()
    for index, image in enumerate(selected):
        shutil.copy2(image.local_path, selected_dir / f"{index:03d}.jpg")
    (project_dir / "article.json").write_text(brief.model_dump_json(indent=2), encoding="utf-8")
    title_match_scores = {image.id: _title_match_score(source_brief.title, image, tag_by_id.get(image.id)) for image in selected}
    (project_dir / "image_tags.json").write_text(json.dumps({"images": [image.model_dump(mode="json") for image in article_images], "tags": [tag.model_dump(mode="json") for tag in tags], "selected_ids": [image.id for image in selected], "selected_asset_order": [image.id for image in selected], "title_match_scores": title_match_scores, "opening_image_reason": "title_match_score_then_hero_overview_relevance", "transitions": [context.model_dump(mode="json") for context in contexts]}, ensure_ascii=False, indent=2), encoding="utf-8")
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
    selected_by_index = {index: image for index, image in enumerate(selected)}
    tag_by_id = {tag.image_id: tag for tag in tags}
    enriched_assets = []
    for index, asset in enumerate(assets):
        source = selected_by_index.get(index)
        tag = tag_by_id.get(source.id) if source else None
        profile = ImageSemanticProfile(role=tag.role.value if tag else "other", narrative_function="evidence" if tag and tag.role.value in {"evidence", "data", "diagram"} else "context", contains_text=None, is_screenshot=bool(source and source.source_url.startswith("screenshot://")), is_data_chart=tag.role.value in {"data", "diagram"} if tag else None, importance=tag.salience if tag else .5, information_density=.75 if tag and tag.role.value in {"data", "diagram"} else .35, source_caption=source.caption if source else "", generated_description=source.alt if source else "")
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
    bundle = resolve_timeline(actions, profiles, title=brief.title, body=brief.text, summary=brief.summary, layout_context=article_context(brief), layout_preferences=preference_summary)
    missing_state = [state.segment_id for state in bundle.resolved if not state.resolved_layout_id or not state.resolved_copy_id]
    if missing_state:
        raise ValueError(f"URL 布局状态不完整，无法安全渲染：{', '.join(missing_state)}")
    (project_dir / "scene_narrative_plan.json").write_text(json.dumps({"narratives": [item.model_dump(mode="json") for item in bundle.narratives.values()]}, ensure_ascii=False, indent=2), encoding="utf-8")
    layout_plan = LayoutPlan(global_style="editorial", scenes=list(bundle.layouts.values()))
    (project_dir / "layout_plan.json").write_text(layout_plan.model_dump_json(indent=2), encoding="utf-8")
    qa = {"layout_director": bundle.layout_diagnostics, "preference_memory": preference_summary, "invalidation_matrix": {"all_hold": "none", "media_replace": ["geometry", "crop", "subject", "contrast"], "copy_replace_or_hide": ["typography", "wrapping", "overflow", "contrast", "visibility"], "layout_adapt": ["changed_blocks", "collision"], "layout_replace": ["full_chromium_audit", "visual_critic"]}, "segments": []}
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
        "video_copy_source": "localized_copy",
        "render_path": "url_layout_renderer",
    }
    persist_diagnostics()
    project = VideoProject(project_id=project_id, fps=REFERENCE_FPS, width=REFERENCE_WIDTH, height=REFERENCE_HEIGHT, images=assets, audio=AudioConfig(path=f"audio/{copied_audio.name}", source_path=f"audio/{copied_audio.name}", duration=max(item.end_frame for item in timeline) / REFERENCE_FPS, sample_rate=analysis.sample_rate, bpm=analysis.bpm), timeline=updated_timeline, output=output, video_copy=copy)
    progress("编排动态布局视频")
    project = compile_render_plan(project, _storyboard_from_timeline(project), creative_plan=None)
    # Rendered previews are durable QA evidence and are generated with the
    # exact same composition, bundled fonts, and media URL strategy as final.
    previews_root = project_dir / "layout" / "previews"
    for index, item in enumerate(project.timeline):
        scene_record = qa["segments"][index]
        scene_dir = previews_root / item.resolved_state.segment_id
        preview_paths = []
        frames = {"settled": min(item.end_frame - 1, item.start_frame + 12), "middle": item.start_frame + item.duration_frames // 2}
        if any(block.typography_role.value == "caption" for block in item.layout.text_blocks):
            frames["caption"] = min(item.end_frame - 1, item.start_frame + max(12, item.duration_frames // 3))
        try:
            for label, frame in frames.items():
                path = render_layout_still(project, repo_root / "remotion", scene_dir / f"{label}.png", frame)
                preview_paths.append(str(path))
                audit_path = path.with_suffix(".audit.json")
                if audit_path.is_file():
                    scene_record.setdefault("remotion_dom_audits", []).append(json.loads(audit_path.read_text(encoding="utf-8")))
            rendered = scene_record.get("rendered") or {}
            critic = critique_scene(rendered_ok=bool(rendered.get("passed")), hard_issues=[], preview_paths=preview_paths, scene_purpose=item.narrative.scene_purpose)
            scene_record["preview_paths"] = preview_paths
            scene_record["visual_critic"] = critic.model_dump(mode="json")
        except Exception as exc:
            scene_record["preview_error"] = str(exc)
    (project_dir / "layout_qa.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")
    session_data = {"source": brief.model_dump(mode="json"), "music_track": track.model_dump(mode="json"), "transition_contexts": [item.model_dump(mode="json") for item in contexts], "project": project.model_dump(mode="json")}
    (project_dir / "session.json").write_text(json.dumps(session_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return project, session_data


def _storyboard_from_timeline(project: VideoProject):
    from content_creator.schemas import DirectorPlan, DirectorTimelineItem
    from content_creator.agents.director_agent import plan_to_storyboard
    return plan_to_storyboard(DirectorPlan(timeline=[DirectorTimelineItem(asset_id=item.asset_id, duration_frames=item.duration_frames, transition=item.transition, transition_strength=item.transition.intensity, reason="URL reference reel") for item in project.timeline]), "reference_reel")
