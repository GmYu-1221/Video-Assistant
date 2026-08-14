import pytest

from content_creator.schemas import CompositionSpec, LayoutPreset, LayoutSpec, LayerSource, LayerType, Region, SceneSpec, TextStyle, TransitionPreset, TransitionSpec, VisualLayer, VisualSpec
from content_creator.services.visual_spec_compiler import expand_transition_preset
from content_creator.services.visual_spec_validator import validate_visual_spec


def test_center_stage_spec_is_valid():
    spec = VisualSpec(composition=CompositionSpec(width=1080, height=1920, fps=30, duration_frames=60), layout=LayoutSpec(preset=LayoutPreset.center_stage, regions={"stage": Region(x=0, y=450, width=1080, height=610, overflow="hidden")}), scenes=[SceneSpec(id="scene-01", start_frame=0, duration_frames=60, layers=[VisualLayer(id="image-01", type=LayerType.image, region="stage", source=LayerSource(asset_id="image-001"))])])
    assert spec.layout.preset == LayoutPreset.center_stage


def test_flash_zoom_blur_expands_to_four_synchronized_tracks():
    transition = TransitionSpec(id="t", from_scene="one", to_scene="two", start_frame=51, duration_frames=9, preset=TransitionPreset.flash_zoom_blur)
    expanded = expand_transition_preset(transition, "image-02")
    assert [track.property.value for track in expanded.tracks] == ["opacity", "transform.scale", "filter.blur", "overlay.opacity"]
    assert [(key.frame, key.value) for key in expanded.tracks[0].keyframes] == [(0, .35), (7, 1)]
    assert [(key.frame, key.value) for key in expanded.tracks[1].keyframes] == [(0, 1.12), (7, 1)]
    assert [(key.frame, key.value) for key in expanded.tracks[2].keyframes] == [(0, 24), (7, 0)]
    assert [(key.frame, key.value) for key in expanded.tracks[3].keyframes] == [(0, 0), (2, .95), (9, 0)]
    assert expanded.tracks[3].target == "transition-overlay"


def test_vertical_stretch_blur_uses_registered_tracks():
    transition = TransitionSpec(id="t", from_scene="one", to_scene="two", start_frame=51, duration_frames=9, preset=TransitionPreset.vertical_stretch_blur)
    expanded = expand_transition_preset(transition, "image-02")
    assert [track.property.value for track in expanded.tracks] == ["opacity", "transform.scaleY", "filter.blur", "overlay.opacity"]
    assert [(key.frame, key.value) for key in expanded.tracks[1].keyframes] == [(0, 1.12), (7, 1)]
    assert [(key.frame, key.value) for key in expanded.tracks[2].keyframes] == [(0, 28), (7, 0)]
    assert [(key.frame, key.value) for key in expanded.tracks[3].keyframes] == [(0, 0), (2, .75), (9, 0)]


def test_text_layers_require_validated_text_style():
    with pytest.raises(ValueError, match="require text_style"):
        VisualLayer(id="copy", type=LayerType.text, region="stage")
    with pytest.raises(ValueError, match="instead of style"):
        VisualLayer(id="copy", type=LayerType.text, region="stage", text_style=TextStyle(color="#FFFFFF", font_size=24, line_height=1.2, max_lines=2), style={"color": "red"})


def test_scene_track_cannot_exceed_scene_duration():
    with pytest.raises(ValueError, match="exceeds scene duration"):
        SceneSpec(id="scene", start_frame=0, duration_frames=10, layers=[VisualLayer(id="image", type=LayerType.image, region="stage", tracks=[{"property": "filter.blur", "keyframes": [{"frame": 0, "value": 20}, {"frame": 11, "value": 0}]}])])


def test_validator_rejects_transition_between_non_adjacent_scenes():
    spec = VisualSpec.model_validate({"composition": {"width": 100, "height": 100, "fps": 30, "duration_frames": 30}, "layout": {"preset": "fullscreen", "regions": {"main": {"x": 0, "y": 0, "width": 100, "height": 100}}}, "scenes": [{"id": "a", "start_frame": 0, "duration_frames": 10, "layers": [{"id": "a-image", "type": "image", "region": "main"}]}, {"id": "b", "start_frame": 10, "duration_frames": 10, "layers": [{"id": "b-image", "type": "image", "region": "main"}]}, {"id": "c", "start_frame": 20, "duration_frames": 10, "layers": [{"id": "c-image", "type": "image", "region": "main"}]}], "transitions": [{"id": "t", "from_scene": "a", "to_scene": "c", "start_frame": 9, "duration_frames": 1}]})
    with pytest.raises(ValueError, match="adjacent"):
        validate_visual_spec(spec)
