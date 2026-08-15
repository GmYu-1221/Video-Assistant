"""Staged URL timeline resolution.

Actions stop at this boundary. Downstream renderers receive only fully resolved
media, copy, layout and visibility state.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256

from content_creator.schemas import (
    BoundaryAction, ContentVariant, CopyAction, DirectorTimelineAction,
    ImageSemanticProfile, LayoutAction, NarrativeContent, PartialTimelineItem,
    ResolvedTimelineItem, SceneLayoutSpec, SceneNarrative, StateAction,
)
from content_creator.services.layout.fallback import solve_scene
from content_creator.services.layout.validator import validate_scene_layout
from content_creator.agents.layout_director import create_layout_plan
from content_creator.services.layout.copy_density import build_variants


@dataclass
class ResolvedBundle:
    actions: list[DirectorTimelineAction]
    partial: list[PartialTimelineItem]
    resolved: list[ResolvedTimelineItem]
    narratives: dict[str, SceneNarrative]
    layouts: dict[str, SceneLayoutSpec]
    segment_narratives: dict[str, SceneNarrative]
    segment_layouts: dict[str, SceneLayoutSpec]
    audit: list[dict]
    layout_diagnostics: dict


def default_url_actions(timeline, assets) -> list[DirectorTimelineAction]:
    """Continuity-aware deterministic Director fallback for URL projects."""
    actions: list[DirectorTimelineAction] = []
    for index, item in enumerate(timeline):
        if index == 0:
            media, copy, layout, boundary, scene = StateAction.replace, CopyAction.replace, LayoutAction.replace, BoundaryAction.continuous, "scene-000"
            sources, purpose = ["article:title"], "opening"
        else:
            scene_cut = index % 3 == 0
            boundary = BoundaryAction.scene_cut if scene_cut else BoundaryAction.accent if index % 2 else BoundaryAction.continuous
            scene = f"scene-{index // 3:03d}"
            media, copy = StateAction.replace, CopyAction.replace
            layout = LayoutAction.replace if scene_cut else LayoutAction.adapt
            sources = ["article:conclusion" if index == len(timeline) - 1 else f"article:body:{index - 1}"]
            purpose = "conclusion" if index == len(timeline) - 1 else "explanation" if index == 1 else "evidence"
        actions.append(DirectorTimelineAction(
            segment_id=f"segment-{index:03d}", scene_id=scene,
            duration_frames=item.duration_frames, scene_purpose=purpose,
            media_action=media, copy_action=copy, layout_action=layout,
            boundary_action=boundary,
            replacement_media_id=item.asset_id if media == StateAction.replace else None,
            narrative_source_ids=sources, transition=item.transition,
            reason="Continuity-aware URL Director fallback.",
        ))
    return actions


def validate_and_partially_resolve(actions: list[DirectorTimelineAction], media_ids: set[str]) -> list[PartialTimelineItem]:
    if not actions:
        raise ValueError("Director timeline must not be empty")
    seen_segments: set[str] = set()
    current_media: str | None = None
    previous_scene: str | None = None
    partial: list[PartialTimelineItem] = []
    for index, action in enumerate(actions):
        if action.segment_id in seen_segments:
            raise ValueError(f"duplicate segment_id: {action.segment_id}")
        seen_segments.add(action.segment_id)
        if index == 0 and (action.media_action == StateAction.hold or action.copy_action == CopyAction.hold or action.layout_action == LayoutAction.hold):
            raise ValueError("first segment cannot hold uninitialized state")
        if action.boundary_action == BoundaryAction.scene_cut and previous_scene == action.scene_id:
            raise ValueError("scene_cut must enter a new scene_id")
        if index and action.boundary_action in {BoundaryAction.continuous, BoundaryAction.accent} and previous_scene != action.scene_id:
            raise ValueError("continuous/accent cannot change scene_id")
        if action.media_action == StateAction.replace:
            if action.replacement_media_id not in media_ids:
                raise ValueError(f"unknown replacement media: {action.replacement_media_id}")
            current_media = action.replacement_media_id
        if current_media is None:
            raise ValueError("media state is not initialized")
        partial.append(PartialTimelineItem(
            segment_id=action.segment_id, scene_id=action.scene_id,
            duration_frames=action.duration_frames, scene_purpose=action.scene_purpose,
            resolved_media_id=current_media, copy_action=action.copy_action,
            layout_action=action.layout_action, boundary_action=action.boundary_action,
            narrative_source_ids=action.narrative_source_ids, transition=action.transition,
        ))
        previous_scene = action.scene_id
    return partial


def _sentences(text: str) -> list[str]:
    boilerplate = ("当前文章被以下社区和专栏收录", "作者 |", "出品 |", "版权声明", "免责声明")
    ui_tokens = ("评论", "分享", "复制链接", "扫一扫", "举报", "收藏")
    parts = [part.strip() for part in re.split(r"(?<=[。！？!?])\s*|\n+", text)]
    return [part for part in parts if len(part) >= 8 and not any(token in part for token in boilerplate) and not any(token in part for token in ui_tokens)]


def _variants(text: str) -> tuple[str, str, str]:
    clean = re.sub(r"\s+", " ", text).strip()
    if clean.lower() in {"图片", "image", "未命名"} or len(clean) < 2:
        clean = "文章核心信息"
    variants = build_variants(clean)
    if variants:
        return variants
    sentences = _sentences(clean) or [clean]
    full = "".join(sentences)[:800]
    short = "".join(sentences[:2])[:400]
    micro = sentences[0][:180]
    return full, short, micro


def freeze_narratives(partial: list[PartialTimelineItem], *, title: str, body: str, summary: str) -> tuple[dict[str, SceneNarrative], dict[str, str | None]]:
    sentences = _sentences(body)
    narratives: dict[str, SceneNarrative] = {}
    segment_copy: dict[str, str | None] = {}
    current_copy: str | None = None
    visible = False
    used_sources: set[str] = set()
    sentence_cursor = 0
    for index, item in enumerate(partial):
        if item.copy_action == CopyAction.replace:
            purpose = item.scene_purpose or ("opening" if index == 0 else "conclusion" if index == len(partial) - 1 else "evidence")
            # Freeze two independent, article-grounded semantic units whenever
            # the source has enough text. The layout solver can then create a
            # title/explanation hierarchy instead of repeating one short line.
            sources: list[tuple[str, str, int | None]] = []
            if purpose == "opening":
                sources.append((title, "title", None))
                if summary:
                    sources.append((summary, "summary", None))
            elif purpose == "conclusion" and sentences:
                sources.append((sentences[-1], "body", len(sentences) - 1))
                if len(sentences) > 1:
                    sources.append((sentences[-2], "body", len(sentences) - 2))
            else:
                while sentence_cursor < len(sentences) and re.sub(r"\s+", " ", sentences[sentence_cursor]).strip() in used_sources:
                    sentence_cursor += 1
                for offset in range(2):
                    source_index = sentence_cursor + offset
                    if source_index < len(sentences):
                        sources.append((sentences[source_index], "body", source_index))
                sentence_cursor += len(sources)
            if not sources:
                sources = [(summary or body or title, "summary" if summary else "body", None)]
            contents: list[NarrativeContent] = []
            for content_index, (source, source_kind, source_index) in enumerate(sources[:2]):
                normalized_source = re.sub(r"\s+", " ", source).strip()
                if normalized_source in used_sources and len(sources) > 1:
                    continue
                full, short, micro = _variants(source)
                digest = sha256(f"{item.segment_id}:{content_index}:{normalized_source}".encode()).hexdigest()[:12]
                content = NarrativeContent(
                    semantic_unit_id=f"semantic-{digest}", content_id="primary" if content_index == 0 else f"support-{content_index}",
                    full=full, short=short, micro=micro, source_kind=source_kind,
                    source_index=source_index, source_hash=sha256(normalized_source.encode("utf-8")).hexdigest(),
                )
                contents.append(content)
                used_sources.add(normalized_source)
            # A title-only page may not have a usable second unit; this is a
            # truthful one-block narrative rather than duplicated variants.
            if not contents:
                contents = [NarrativeContent(semantic_unit_id=f"semantic-{item.segment_id}", content_id="primary", full=title, short=title, micro=title, source_kind="title", source_hash=sha256(title.encode()).hexdigest())]
            digest = sha256(f"{item.segment_id}:{contents[0].source_hash}".encode()).hexdigest()[:12]
            copy_id = f"copy-{digest}"
            unit_id = f"semantic-{digest}"
            source_kind = "title" if purpose == "opening" else "body"
            narratives[copy_id] = SceneNarrative(copy_id=copy_id, scene_id=item.scene_id, asset_id=item.resolved_media_id, scene_purpose=purpose, contents=contents)
            current_copy, visible = copy_id, True
        elif item.copy_action == CopyAction.hide:
            visible = False
        elif current_copy is None:
            raise ValueError("copy hold references uninitialized state")
        segment_copy[item.segment_id] = current_copy if visible else None
    return narratives, segment_copy


def _bind_layout(layout: SceneLayoutSpec, narrative: SceneNarrative, media_id: str) -> SceneLayoutSpec:
    primary = narrative.contents[0]
    media = [block.model_copy(update={"asset_id": media_id}) for block in layout.media_blocks]
    text = [block.model_copy(update={"content_id": primary.content_id, "semantic_unit_id": primary.semantic_unit_id, "content_hash": primary.content_hash(block.variant_id)}) for block in layout.text_blocks]
    return layout.model_copy(update={"scene_id": narrative.scene_id, "media_blocks": media, "text_blocks": text})


def resolve_timeline(actions: list[DirectorTimelineAction], media_profiles: dict[str, ImageSemanticProfile | None], *, title: str, body: str, summary: str, layout_context: dict | None = None, layout_preferences: dict | None = None) -> ResolvedBundle:
    partial = validate_and_partially_resolve(actions, set(media_profiles))
    narratives, segment_copy = freeze_narratives(partial, title=title, body=body, summary=summary)
    request_narratives: dict[str, SceneNarrative] = {}
    request_items: list[tuple[SceneNarrative, ImageSemanticProfile | None]] = []
    active_copy: SceneNarrative | None = None
    for item in partial:
        copy_id = segment_copy[item.segment_id]
        if copy_id is not None:
            active_copy = narratives[copy_id]
        if active_copy is None:
            raise ValueError("visible segment has no frozen copy")
        request_narrative = active_copy.model_copy(update={"scene_id": item.segment_id, "asset_id": item.resolved_media_id})
        request_narratives[item.segment_id] = request_narrative
        request_items.append((request_narrative, media_profiles[item.resolved_media_id]))
    directed_plan, layout_diagnostics = create_layout_plan(
        request_items,
        global_style="editorial",
        context=layout_context,
        preferences=layout_preferences,
    )
    directed_by_segment = {scene.scene_id: scene for scene in directed_plan.scenes}
    layouts: dict[str, SceneLayoutSpec] = {}
    segment_layouts: dict[str, SceneLayoutSpec] = {}
    segment_narratives: dict[str, SceneNarrative] = {}
    resolved: list[ResolvedTimelineItem] = []
    audit: list[dict] = []
    current_layout: SceneLayoutSpec | None = None
    current_copy: SceneNarrative | None = None
    cursor = 0
    for item in partial:
        copy_id = segment_copy[item.segment_id]
        if copy_id is not None:
            current_copy = narratives[copy_id]
        request_narrative = request_narratives[item.segment_id]
        runtime_narrative = request_narrative.model_copy(update={"scene_id": item.scene_id})
        directed = directed_by_segment[item.segment_id].model_copy(update={"scene_id": item.scene_id})
        requested = item.layout_action
        resolved_action = requested
        override_reason = None
        if requested == LayoutAction.replace or current_layout is None:
            layout = directed
            parent = current_layout.layout_id if current_layout else None
            layout = layout.model_copy(update={"layout_id": f"layout-{item.segment_id}", "parent_layout_id": parent, "change_mode": "root" if parent is None else "replace", "changed_block_ids": [block.block_id for block in [*layout.media_blocks, *layout.text_blocks]]})
            layouts[layout.layout_id] = layout
        elif requested == LayoutAction.adapt:
            candidate = directed
            layout = candidate.model_copy(update={"layout_id": f"layout-{item.segment_id}", "parent_layout_id": current_layout.layout_id, "change_mode": "adapt", "changed_block_ids": ["media", "primary-copy"]})
            layouts[layout.layout_id] = layout
        else:
            layout = _bind_layout(current_layout, runtime_narrative, item.resolved_media_id)
        issues = validate_scene_layout(layout, runtime_narrative, media_profiles[item.resolved_media_id])
        if issues and requested == LayoutAction.hold:
            candidate = directed
            layout = candidate.model_copy(update={"layout_id": f"layout-{item.segment_id}", "parent_layout_id": current_layout.layout_id, "change_mode": "adapt", "changed_block_ids": sorted({issue.block_id for issue in issues if issue.block_id} or {"primary-copy"})})
            layouts[layout.layout_id] = layout
            resolved_action = LayoutAction.adapt
            override_reason = ",".join(sorted({issue.code for issue in issues}))
        current_layout = layout
        segment_layouts[item.segment_id] = layout
        segment_narratives[item.segment_id] = runtime_narrative
        end = cursor + item.duration_frames
        resolved.append(ResolvedTimelineItem(segment_id=item.segment_id, scene_id=item.scene_id, start_frame=cursor, end_frame=end, duration_frames=item.duration_frames, resolved_media_id=item.resolved_media_id, resolved_copy_id=copy_id, resolved_layout_id=layout.layout_id, visibility="visible" if copy_id else "hidden", boundary_action=item.boundary_action, requested_layout_action=requested, resolved_layout_action=resolved_action, override_reason=override_reason, transition=item.transition))
        audit.append({"segment_id": item.segment_id, "requested_layout_action": requested.value, "resolved_layout_action": resolved_action.value, "override_reason": override_reason})
        cursor = end
    return ResolvedBundle(actions=actions, partial=partial, resolved=resolved, narratives=narratives, layouts=layouts, segment_narratives=segment_narratives, segment_layouts=segment_layouts, audit=audit, layout_diagnostics=layout_diagnostics)
