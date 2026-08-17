from types import SimpleNamespace

from content_creator.schemas import (
    BackgroundTreatment, BoundaryAction, ContentVariant, CopyAction,
    DirectorTimelineAction, ImageSemanticProfile, LayoutAction, MediaBlock,
    NarrativeContent, OverlayPolicy, PartialTimelineItem, Rect,
    ResolvedTimelineItem, SceneLayoutSpec, SceneNarrative, StateAction,
    TextBlock, TransitionConfig, TypographyRole,
)
from content_creator.services import url_video


def _bundle(segment_count: int, characters: int, density: float = .35):
    actions = []
    partial = []
    resolved = []
    narratives = {}
    layouts = {}
    profiles = {}
    cursor = 0
    for index in range(segment_count):
        segment_id = f"segment-{index:03d}"
        media_id = f"image-{index:03d}"
        text = "正文" * max(1, characters // 2)
        content = NarrativeContent(
            semantic_unit_id=f"semantic-{index}", content_id="primary",
            full=text, short=text, micro=text[:180], source_kind="body",
        )
        narrative = SceneNarrative(copy_id=f"copy-{index}", scene_id=f"scene-{index}", asset_id=media_id, scene_purpose="explanation", contents=[content])
        block = TextBlock(
            block_id="primary-copy", content_id="primary", semantic_unit_id=content.semantic_unit_id,
            variant_id=ContentVariant.micro, content_hash=content.content_hash(ContentVariant.micro),
            bbox=Rect(x=80, y=1120, width=920, height=300), typography_role=TypographyRole.caption,
            font_id="noto-sans-sc", max_lines=3,
        )
        layout = SceneLayoutSpec(
            layout_id=f"layout-{index}", scene_id=f"scene-{index}", background=BackgroundTreatment(),
            media_blocks=[MediaBlock(block_id="media", asset_id=media_id, bbox=Rect(x=0, y=430, width=1080, height=610), fit="contain")],
            text_blocks=[block], overlay_policy=OverlayPolicy(),
        )
        transition = TransitionConfig(duration_frames=6)
        action = DirectorTimelineAction(
            segment_id=segment_id, scene_id=f"scene-{index}", duration_frames=60,
            scene_purpose="explanation", media_action=StateAction.replace,
            copy_action=CopyAction.replace, layout_action=LayoutAction.replace,
            boundary_action=BoundaryAction.continuous if index == 0 else BoundaryAction.scene_cut,
            replacement_media_id=media_id, narrative_source_ids=[f"article:body:{index}"], transition=transition,
        )
        actions.append(action)
        partial.append(PartialTimelineItem(
            segment_id=segment_id, scene_id=f"scene-{index}", duration_frames=60,
            scene_purpose="explanation", resolved_media_id=media_id, copy_action=CopyAction.replace,
            layout_action=LayoutAction.replace, boundary_action=action.boundary_action,
            narrative_source_ids=action.narrative_source_ids, transition=transition,
        ))
        resolved.append(ResolvedTimelineItem(
            segment_id=segment_id, scene_id=f"scene-{index}", start_frame=cursor, end_frame=cursor + 60,
            duration_frames=60, resolved_media_id=media_id, resolved_copy_id=f"copy-{index}",
            resolved_layout_id=layout.layout_id, boundary_action=action.boundary_action,
            requested_layout_action=LayoutAction.replace, resolved_layout_action=LayoutAction.replace,
            transition=transition,
        ))
        cursor += 60
        narratives[segment_id] = narrative
        layouts[segment_id] = layout
        profiles[media_id] = ImageSemanticProfile(information_density=density)
    return SimpleNamespace(actions=actions, partial=partial, resolved=resolved, segment_narratives=narratives, segment_layouts=layouts), profiles


def test_asset_target_allows_one_asset_by_default(monkeypatch):
    monkeypatch.delenv("URL_ASSET_TARGET_MIN", raising=False)
    assert url_video._asset_target_count(120) == 1


def test_single_segment_is_retimed_between_three_and_six_seconds():
    bundle, profiles = _bundle(1, 8)
    diagnostics = url_video._retime_resolved_bundle(bundle, profiles, bpm=120, fps=30)
    duration = bundle.resolved[0].duration_frames / 30
    assert 3 <= duration <= 6
    assert diagnostics[0]["visible_character_count"] == 8
    assert bundle.actions[0].duration_frames == bundle.resolved[0].duration_frames


def test_multiple_segments_are_retimed_without_exceeding_seven_seconds():
    bundle, profiles = _bundle(3, 120, density=.9)
    url_video._retime_resolved_bundle(bundle, profiles, bpm=90, fps=30)
    assert all(3 <= item.duration_frames / 30 <= 7 for item in bundle.resolved)
    assert [item.start_frame for item in bundle.resolved] == [0, bundle.resolved[0].end_frame, bundle.resolved[1].end_frame]
