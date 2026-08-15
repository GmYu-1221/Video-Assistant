"""Compatibility adapter from the legacy project timeline to Visual Spec 2.0."""
from __future__ import annotations

from content_creator.schemas import (
    CompositionSpec, ImageAsset, LayoutPreset, LayoutSpec, LayerSource, LayerType,
    Region, SceneSpec, TextStyle, TransitionPreset, TransitionSpec, VideoProject, VisualLayer,
    VisualSpec, VisualSpecDecision,
)
from content_creator.schemas.visual_spec import AnimatableProperty, AnimationTrack, EasingType, Keyframe
from content_creator.services.visual_spec_compiler import expand_transition_preset
from content_creator.services.visual_spec_validator import validate_visual_spec


def project_to_visual_spec(project: VideoProject, stage: Region | None = None, decision: VisualSpecDecision | None = None) -> VisualSpec:
    """Create a deterministic center-stage spec without invoking an LLM."""
    # URL projects with a LayoutPlan are rendered by SceneLayoutRenderer. Keep a
    # small valid VisualSpec shell for legacy composition selection, but never
    # inject the reference-reel header/stage/footer template into their data.
    if any(item.layout is not None for item in project.timeline):
        regions = {"dynamic": Region(x=0, y=0, width=project.width, height=project.height)}
        scenes = []
        for index, item in enumerate(project.timeline):
            asset = next((candidate for candidate in project.images if candidate.id == item.asset_id), None)
            if asset is None:
                continue
            scenes.append(SceneSpec(id=f"scene-{index}", start_frame=item.start_frame, duration_frames=item.duration_frames, layers=[VisualLayer(id=f"dynamic-{index}", type=LayerType.image, region="dynamic", source=LayerSource(asset_id=asset.id))]))
        return validate_visual_spec(VisualSpec(composition=CompositionSpec(width=project.width, height=project.height, fps=project.fps, duration_frames=max((scene.start_frame + scene.duration_frames for scene in scenes), default=1)), layout=LayoutSpec(preset=LayoutPreset.fullscreen, regions=regions), scenes=scenes))
    is_reference_layout = project.width == 1080 and project.height == 1920
    stage = stage or Region(x=0, y=430 if is_reference_layout else 450, width=project.width, height=610 if is_reference_layout else min(610, project.height), overflow="hidden")
    regions = {"stage": stage}
    persistent_layers = []
    if is_reference_layout:
        regions.update({
            "header": Region(x=60, y=120, width=960, height=260),
            "footer": Region(x=80, y=1100, width=920, height=540),
        })
        copy = project.video_copy
        if copy.headline:
            persistent_layers.append(VisualLayer(id="headline", type=LayerType.text, region="header", source=LayerSource(content=copy.headline), text_style=TextStyle(color="#DCE74A", font_size=48, line_height=1.3, font_weight=600, max_lines=2)))
        if copy.subtitle:
            persistent_layers.append(VisualLayer(id="subtitle", type=LayerType.text, region="header", source=LayerSource(content=copy.subtitle), text_style=TextStyle(color="#FFFFFF", font_size=30, line_height=1.3, font_weight=400, max_lines=2, top_offset=142)))
        if copy.body:
            persistent_layers.append(VisualLayer(id="body", type=LayerType.text, region="footer", source=LayerSource(content=copy.body), text_style=TextStyle(color="#DDDDDD", font_size=30, line_height=1.65, font_weight=400, max_lines=8)))
    decisions = {(entry.from_asset_id, entry.to_asset_id): entry for entry in (decision.transitions if decision else [])}
    scenes = []
    transitions = []
    for index, item in enumerate(project.timeline):
        asset = next((candidate for candidate in project.images if candidate.id == item.asset_id), None)
        if asset is None:
            continue
        push_tracks = []
        if item.duration_frames > 1:
            push_start = min(9, item.duration_frames - 1)
            push_tracks = [AnimationTrack(property=AnimatableProperty.scale, keyframes=[Keyframe(frame=push_start, value=1, easing=EasingType.linear), Keyframe(frame=item.duration_frames, value=1.025, easing=EasingType.linear)])]
        layer = VisualLayer(id=f"scene-{index}-image", type=LayerType.image, region="stage", source=LayerSource(asset_id=asset.id), style={"object_fit": "cover"} if is_reference_layout else {}, tracks=push_tracks)
        scenes.append(SceneSpec(id=f"scene-{index}", start_frame=item.start_frame, duration_frames=item.duration_frames, layers=[layer]))
        if index:
            previous = project.timeline[index - 1]
            duration = min(9, item.duration_frames, previous.duration_frames)
            selected = decisions.get((previous.asset_id, item.asset_id))
            preset = selected.preset if selected else TransitionPreset.flash_zoom_blur
            if selected is None:
                first_late_boundary = (2 * len(project.timeline) + 2) // 3
                late_boundaries = range(max(1, first_late_boundary), len(project.timeline))
                strongest_late_boundary = max(late_boundaries, key=lambda boundary: project.timeline[boundary - 1].transition.intensity, default=None)
                if index == strongest_late_boundary:
                    preset = TransitionPreset.vertical_stretch_blur
            params = selected.params if selected else {"blur_px": 28 if preset == TransitionPreset.vertical_stretch_blur else 24, "flash_peak": 0.75 if preset == TransitionPreset.vertical_stretch_blur else 0.95}
            transitions.append(TransitionSpec(id=f"transition-{index - 1}-{index}", from_scene=f"scene-{index - 1}", to_scene=f"scene-{index}", start_frame=item.start_frame - duration, duration_frames=duration, preset=preset, params=params))
    duration_frames = max((scene.start_frame + scene.duration_frames for scene in scenes), default=1)
    preset = decision.layout_preset if decision else LayoutPreset.center_stage
    spec = VisualSpec(composition=CompositionSpec(width=project.width, height=project.height, fps=project.fps, duration_frames=duration_frames), layout=LayoutSpec(preset=preset, regions=regions), persistent_layers=persistent_layers, scenes=scenes, transitions=[expand_transition_preset(transition, scenes[index + 1].layers[0].id) for index, transition in enumerate(transitions)])
    return validate_visual_spec(spec)
