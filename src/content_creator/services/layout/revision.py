"""Typography-only revisions derived from an already rendered URL project."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from content_creator.agents.layout_director import create_layout_plan
from content_creator.schemas import ArticleBrief, ContentVariant, CopyDensityIntent, ImageSemanticProfile, LayoutPlan, TimelineItem, VideoProject
from content_creator.services.layout.copy_density import detect_copy_density_intent, expand_project_narratives
from content_creator.services.layout.fallback import solve_plan
from content_creator.services.layout.qa import validate_rendered_layout, validate_rendered_persistent_title
from content_creator.services.layout.persistent_title import build_persistent_title
from content_creator.services.layout.validator import normalized_layout_fingerprint, validate_persistent_title, validate_scene_layout


VERSION_ARTIFACTS = (
    "director_timeline.json", "scene_narrative_plan.json", "layout_plan.json",
    "layout_qa.json", "session.json", "viral_copy_plan.json", "final_artifact_validation.json",
)


def _repair_rendered_overflow(layout, narrative, rendered):
    content = {item.content_id: item for item in narrative.contents}
    overflow_ids = {issue.block_id for issue in rendered.issues if issue.code == "rendered_overflow" and issue.block_id}
    repaired = []
    for block in layout.text_blocks:
        if block.block_id not in overflow_ids:
            repaired.append(block)
            continue
        measured = rendered.blocks.get(block.block_id, {})
        horizontal_overflow = max(0, int(measured.get("scrollWidth", block.bbox.width)) - int(measured.get("clientWidth", block.bbox.width)))
        vertical_overflow = max(0, int(measured.get("scrollHeight", block.bbox.height)) - int(measured.get("clientHeight", block.bbox.height)))
        width = min(960, block.bbox.width + horizontal_overflow + (8 if horizontal_overflow else 0))
        center = block.bbox.x + block.bbox.width / 2
        x = max(60, min(round(center - width / 2), 1020 - width))
        needed = block.bbox.height + vertical_overflow + (8 if vertical_overflow else 0)
        if block.bbox.y < 430:
            maximum = max(block.bbox.height, 430 - block.bbox.y)
        else:
            maximum = max(block.bbox.height, 1860 - block.bbox.y)
        updates: dict[str, Any] = {"bbox": block.bbox.model_copy(update={"x": x, "width": width, "height": min(maximum, max(block.bbox.height, needed))})}
        geometry_exhausted = (horizontal_overflow and width >= 960) or (vertical_overflow and needed > maximum)
        if geometry_exhausted:
            unit = content[block.content_id]
            shorter = {
                ContentVariant.full: ContentVariant.short,
                ContentVariant.short: ContentVariant.micro,
                ContentVariant.micro: ContentVariant.micro,
            }[block.variant_id]
            updates.update({"variant_id": shorter, "content_hash": unit.content_hash(shorter)})
        repaired.append(block.model_copy(update=updates))
    return layout.model_copy(update={"text_blocks": repaired, "changed_block_ids": sorted(set(layout.changed_block_ids) | overflow_ids)})


def project_font_ids(project: VideoProject) -> list[str]:
    fonts = {block.font_id for item in project.timeline if item.layout for block in item.layout.text_blocks}
    if project.persistent_title:
        fonts.add(project.persistent_title.font_id)
    return sorted(fonts)


def project_layout_fingerprints(project: VideoProject) -> list[list[Any]]:
    seen: set[str] = set()
    values = []
    for item in project.timeline:
        if not item.layout or item.layout.layout_id in seen:
            continue
        seen.add(item.layout.layout_id)
        values.append(list(normalized_layout_fingerprint(item.layout)))
    return values


def project_copy_metrics(project: VideoProject) -> dict[str, Any]:
    character_count = 0
    block_count = 0
    variants: list[dict[str, str]] = []
    for item in project.timeline:
        if not item.layout or not item.narrative:
            continue
        content = {entry.content_id: entry for entry in item.narrative.contents}
        for block in item.layout.text_blocks:
            if block.content_id not in content:
                continue
            value = content[block.content_id].value(block.variant_id)
            character_count += len(value)
            block_count += 1
            variants.append({"segment_id": item.resolved_state.segment_id if item.resolved_state else "", "content_id": block.content_id, "variant_id": block.variant_id.value})
    return {"character_count": character_count, "block_count": block_count, "variants": variants}


def write_version_snapshot(project: VideoProject, version_dir: str | Path, *, source_project_dir: str | Path, copy_video_from: str | Path | None = None) -> Path:
    version = Path(version_dir)
    version.mkdir(parents=True, exist_ok=True)
    root = Path(source_project_dir)
    output = project.output.model_copy(update={
        "render_data": str(version / "render_data.json"),
        "final_video": str(version / "final.mp4"),
    })
    snapshot = project.model_copy(update={"output": output})
    (version / "project.json").write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
    (version / "render_data.json").write_text(json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
    for name in VERSION_ARTIFACTS:
        source = root / name
        if source.is_file():
            shutil.copy2(source, version / name)
    if copy_video_from:
        source_video = Path(copy_video_from)
        if source_video.is_file():
            shutil.copy2(source_video, version / "final.mp4")
    return version


def load_version_project(version_dir: str | Path) -> VideoProject:
    path = Path(version_dir) / "project.json"
    return VideoProject.model_validate_json(path.read_text(encoding="utf-8"))


def revise_typography(
    project: VideoProject,
    *,
    revision_id: str,
    reason: str,
    context: dict[str, Any],
    preferences: dict[str, Any],
    remotion_public: str | Path,
    article: ArticleBrief,
) -> tuple[VideoProject, dict[str, Any]]:
    density_intent = detect_copy_density_intent(reason)
    expanded_narratives, density_diagnostics = expand_project_narratives(project, article, density_intent)
    request_items = []
    original_by_segment = {}
    for item in project.timeline:
        if not item.layout or not item.narrative or not item.resolved_state:
            raise ValueError("typography revision requires a fully resolved URL timeline")
        segment_id = item.resolved_state.segment_id
        narrative = expanded_narratives[segment_id]
        profile = next((asset.semantic_profile for asset in project.images if asset.id == item.asset_id), None)
        request_items.append((narrative, profile))
        original_by_segment[segment_id] = item

    previous_fonts = set(project_font_ids(project))
    layout_context = dict(context)
    layout_context["copy_density_intent"] = density_intent.value
    directed, diagnostics = create_layout_plan(
        request_items,
        global_style="editorial",
        context=layout_context,
        preferences=preferences,
        feedback_reason=reason,
        avoid_fonts=previous_fonts,
    )
    directed_by_segment = {scene.scene_id: scene for scene in directed.scenes}
    revised_persistent_title = project.persistent_title
    persistent_title_rendered = None
    if project.persistent_title:
        revised_persistent_title = build_persistent_title(project.persistent_title.content, diagnostics.get("font_palette"))
        title_issues = validate_persistent_title(revised_persistent_title)
        persistent_title_rendered = None if title_issues else validate_rendered_persistent_title(revised_persistent_title, remotion_public)
        if title_issues or not persistent_title_rendered or not persistent_title_rendered.passed:
            codes = [issue.code for issue in title_issues] + ([issue.code for issue in persistent_title_rendered.issues] if persistent_title_rendered else [])
            raise ValueError("固定顶部标题修订校验失败：" + ", ".join(codes))
    directed_fonts = {block.font_id for scene in directed.scenes for block in scene.text_blocks}
    unchanged_geometry = all(
        normalized_layout_fingerprint(directed_by_segment[segment_id]) == normalized_layout_fingerprint(original.layout)
        for segment_id, original in original_by_segment.items()
    )
    unchanged = directed_fonts == previous_fonts and unchanged_geometry
    if unchanged:
        directed = solve_plan(request_items, "editorial", context=context, preferences=preferences, avoid_fonts=previous_fonts)
        directed_by_segment = {scene.scene_id: scene for scene in directed.scenes}
        diagnostics = diagnostics | {"mode": "deterministic_negative_backfill", "avoided_font_ids": sorted(previous_fonts)}

    revised_timeline: list[TimelineItem] = []
    qa_segments = []
    layouts = []
    for item in project.timeline:
        state = item.resolved_state
        assert state and item.layout and item.narrative
        narrative = expanded_narratives[state.segment_id]
        candidate = directed_by_segment[state.segment_id]
        original = item.layout
        layout_id = f"{original.layout_id}-{revision_id}-{state.segment_id}"
        layout = original.model_copy(update={
            "layout_id": layout_id,
            "parent_layout_id": original.layout_id,
            "change_mode": "adapt",
            "changed_block_ids": [block.block_id for block in candidate.text_blocks],
            "text_blocks": candidate.text_blocks,
            "media_blocks": original.media_blocks,
            "background": original.background,
            "scene_id": original.scene_id,
        })
        profile: ImageSemanticProfile | None = next((asset.semantic_profile for asset in project.images if asset.id == item.asset_id), None)
        hard = validate_scene_layout(layout, narrative, profile)
        rendered = None if hard else validate_rendered_layout(layout, narrative, remotion_public)
        for _ in range(2):
            if not rendered or rendered.passed or not rendered.issues or not all(issue.code == "rendered_overflow" for issue in rendered.issues):
                break
            repaired = _repair_rendered_overflow(layout, narrative, rendered)
            if repaired == layout:
                break
            layout = repaired
            hard = validate_scene_layout(layout, narrative, profile)
            rendered = None if hard else validate_rendered_layout(layout, narrative, remotion_public)
        if hard or not rendered or not rendered.passed:
            codes = [issue.code for issue in hard] + ([issue.code for issue in rendered.issues] if rendered else [])
            overflow = {issue.block_id: rendered.blocks.get(issue.block_id or "", {}) for issue in (rendered.issues if rendered else []) if issue.code == "rendered_overflow"}
            overflow_messages = []
            for block_id, measured in overflow.items():
                horizontal = max(0, int(measured.get("scrollWidth", 0)) - int(measured.get("clientWidth", 0)))
                vertical = max(0, int(measured.get("scrollHeight", 0)) - int(measured.get("clientHeight", 0)))
                if horizontal:
                    overflow_messages.append(f"{block_id} 横向溢出 {horizontal}px")
                if vertical:
                    overflow_messages.append(f"{block_id} 纵向溢出 {vertical}px")
            detail = f"; {'; '.join(overflow_messages)}; overflow={json.dumps(overflow, ensure_ascii=False)}" if overflow else ""
            raise ValueError("typography revision failed layout validation: " + ",".join(sorted(set(codes))) + detail)
        revised_state = state.model_copy(update={"resolved_layout_id": layout_id, "resolved_copy_id": narrative.copy_id, "visibility": "visible"})
        revised_timeline.append(item.model_copy(update={"narrative": narrative.model_copy(update={"scene_id": state.scene_id}), "layout": layout, "resolved_state": revised_state}))
        layouts.append(layout)
        qa_segments.append({
            "segment_id": state.segment_id,
            "source_layout_id": original.layout_id,
            "layout_id": layout_id,
            "hard_issues": [],
            "rendered": rendered.model_dump(mode="json"),
        })

    # These fields are the immutable envelope for a typography-only revision.
    revised = project.model_copy(update={"timeline": revised_timeline, "persistent_title": revised_persistent_title})
    for before, after in zip(project.timeline, revised.timeline):
        if (
            before.asset_id != after.asset_id
            or before.start_frame != after.start_frame
            or before.end_frame != after.end_frame
            or before.duration_frames != after.duration_frames
            or before.transition != after.transition
            or before.visual_events != after.visual_events
            or before.layout.media_blocks != after.layout.media_blocks
        ):
            raise ValueError("typography revision attempted to mutate frozen media, timing, motion or transition state")
    if project.audio != revised.audio or project.images != revised.images:
        raise ValueError("typography revision attempted to mutate frozen assets or audio")
    if project.persistent_title and revised.persistent_title and (
        project.persistent_title.content != revised.persistent_title.content
        or project.persistent_title.content_hash != revised.persistent_title.content_hash
        or project.persistent_title.bbox != revised.persistent_title.bbox
    ):
        raise ValueError("typography revision attempted to mutate frozen persistent title content or geometry")
    copy_metrics = {"before": project_copy_metrics(project), "after": project_copy_metrics(revised)}
    if density_intent == CopyDensityIntent.increase and (copy_metrics["after"]["character_count"] <= copy_metrics["before"]["character_count"] or copy_metrics["after"]["block_count"] <= copy_metrics["before"]["block_count"]):
        raise ValueError("没有更多可用正文：修订后的实际字幕内容没有增加")
    qa = {
        "revision_id": revision_id,
        "reason": reason,
        "layout_director": diagnostics,
        "source_font_ids": sorted(previous_fonts),
        "font_ids": project_font_ids(revised),
        "copy_density": density_diagnostics | copy_metrics,
        "persistent_title": {"spec": revised_persistent_title.model_dump(mode="json"), "rendered": persistent_title_rendered.model_dump(mode="json")} if revised_persistent_title and persistent_title_rendered else None,
        "segments": qa_segments,
    }
    return revised, {"layout_plan": LayoutPlan(global_style="editorial", persistent_title=revised_persistent_title, scenes=layouts), "layout_qa": qa}
