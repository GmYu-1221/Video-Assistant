import pytest

from content_creator.schemas import CompositionSpec, LayoutPreset, LayoutSpec, LayerSource, LayerType, Region, SceneSpec, TransitionPreset, TransitionSpec, VisualLayer, VisualSpec
from content_creator.services.visual_spec_compiler import expand_transition_preset


def test_center_stage_spec_is_valid():
    spec = VisualSpec(composition=CompositionSpec(width=1080, height=1920, fps=30, duration_frames=60), layout=LayoutSpec(preset=LayoutPreset.center_stage, regions={"stage": Region(x=0, y=450, width=1080, height=610, overflow="hidden")}), scenes=[SceneSpec(id="scene-01", start_frame=0, duration_frames=60, layers=[VisualLayer(id="image-01", type=LayerType.image, region="stage", source=LayerSource(asset_id="image-001"))])])
    assert spec.layout.preset == LayoutPreset.center_stage


def test_flash_zoom_blur_expands_to_four_synchronized_tracks():
    transition = TransitionSpec(id="t", from_scene="one", to_scene="two", start_frame=57, duration_frames=11, preset=TransitionPreset.flash_zoom_blur, params={"incoming_scale": 1.14, "blur_px": 24, "flash_peak": 0.95})
    expanded = expand_transition_preset(transition, "image-02")
    assert [track.property.value for track in expanded.tracks] == ["opacity", "transform.scale", "filter.blur", "overlay.opacity"]
    assert expanded.tracks[1].keyframes[0].value == 1.14
    assert expanded.tracks[2].keyframes[-1].value == 0
    assert expanded.tracks[3].target == "transition-overlay"


def test_scene_track_cannot_exceed_scene_duration():
    with pytest.raises(ValueError, match="exceeds scene duration"):
        SceneSpec(id="scene", start_frame=0, duration_frames=10, layers=[VisualLayer(id="image", type=LayerType.image, region="stage", tracks=[{"property": "filter.blur", "keyframes": [{"frame": 0, "value": 20}, {"frame": 11, "value": 0}]}])])
