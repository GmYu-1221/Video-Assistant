import pytest

from content_creator.schemas import BoundaryAction, ContentVariant, CopyAction, DirectorTimelineAction, ImageSemanticProfile, LayoutAction, StateAction, TransitionConfig
from content_creator.services.timeline_state import resolve_timeline, validate_and_partially_resolve


def action(segment, scene, *, media=StateAction.hold, copy=CopyAction.hold, layout=LayoutAction.hold, boundary=BoundaryAction.continuous, replacement=None, sources=None):
    return DirectorTimelineAction(segment_id=segment, scene_id=scene, duration_frames=30, media_action=media, copy_action=copy, layout_action=layout, boundary_action=boundary, replacement_media_id=replacement, narrative_source_ids=sources or [], transition=TransitionConfig(), reason="test")


def initial():
    return action("s0", "scene-a", media=StateAction.replace, copy=CopyAction.replace, layout=LayoutAction.replace, replacement="a", sources=["article:title"])


def test_first_segment_cannot_hold_uninitialized_state():
    with pytest.raises(ValueError, match="first segment"):
        validate_and_partially_resolve([action("s0", "scene-a")], {"a"})


def test_scene_cut_requires_new_scene_and_continuous_preserves_scene():
    with pytest.raises(ValueError, match="scene_cut"):
        validate_and_partially_resolve([initial(), action("s1", "scene-a", boundary=BoundaryAction.scene_cut)], {"a"})
    with pytest.raises(ValueError, match="continuous"):
        validate_and_partially_resolve([initial(), action("s1", "scene-b")], {"a"})


def test_hide_then_hold_stays_hidden_until_replace():
    actions = [initial(), action("s1", "scene-a", copy=CopyAction.hide), action("s2", "scene-a")]
    bundle = resolve_timeline(actions, {"a": ImageSemanticProfile()}, title="标题", body="这是第一段正文。还有第二段正文。", summary="结论摘要。")
    assert [state.visibility for state in bundle.resolved] == ["visible", "hidden", "hidden"]
    assert bundle.resolved[1].resolved_copy_id is None
    assert bundle.resolved[2].resolved_copy_id is None


def test_required_continuity_combinations_resolve_to_actual_state():
    actions = [
        initial(),
        action("s1", "scene-a", copy=CopyAction.replace, sources=["article:body:0"]),
        action("s2", "scene-a", media=StateAction.replace, layout=LayoutAction.adapt, boundary=BoundaryAction.accent, replacement="b"),
        action("s3", "scene-b", media=StateAction.replace, copy=CopyAction.replace, layout=LayoutAction.replace, boundary=BoundaryAction.scene_cut, replacement="c", sources=["article:conclusion"]),
    ]
    bundle = resolve_timeline(actions, {key: ImageSemanticProfile() for key in "abc"}, title="标题", body="第一条事实。第二条事实。第三条事实。", summary="最后的结论。")
    first, copy_change, media_change, cut = bundle.resolved
    assert copy_change.resolved_media_id == first.resolved_media_id
    assert copy_change.resolved_copy_id != first.resolved_copy_id
    assert copy_change.resolved_layout_id == first.resolved_layout_id
    assert media_change.resolved_copy_id == copy_change.resolved_copy_id
    assert media_change.resolved_layout_action == LayoutAction.adapt
    assert cut.scene_id != media_change.scene_id
    assert cut.boundary_action == BoundaryAction.scene_cut
    assert cut.resolved_layout_id != media_change.resolved_layout_id
    assert all(not hasattr(state, "media_action") for state in bundle.resolved)


def test_semantic_variants_share_one_unit_and_hold_layout_rebinds_copy():
    actions = [initial(), action("s1", "scene-a", copy=CopyAction.replace, sources=["article:body:0"])]
    bundle = resolve_timeline(actions, {"a": ImageSemanticProfile()}, title="标题", body="第一条有效事实。第二条有效事实。", summary="结论。")
    second = bundle.segment_narratives["s1"].contents[0]
    assert all(second.variant_id(variant).startswith(second.semantic_unit_id) for variant in ContentVariant)
    assert bundle.resolved[0].resolved_layout_id == bundle.resolved[1].resolved_layout_id


def test_opening_dynamic_narrative_does_not_repeat_persistent_title():
    bundle = resolve_timeline([initial()], {"a": ImageSemanticProfile()}, title="固定文章标题", body="第一条有效事实。第二条有效事实。", summary="文章摘要说明。")
    narrative = bundle.segment_narratives["s0"]
    assert all(content.source_kind != "title" for content in narrative.contents)
    assert all("固定文章标题" not in content.full for content in narrative.contents)
    blocks = bundle.segment_layouts["s0"].text_blocks
    assert any(block.bbox.y >= 470 and block.bbox.y + block.bbox.height <= 655 for block in blocks)
    assert any(block.bbox.y >= 1040 for block in blocks)
