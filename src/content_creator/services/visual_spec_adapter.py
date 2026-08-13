"""Compatibility adapter from the legacy project timeline to Visual Spec 2.0."""
from __future__ import annotations

from content_creator.schemas import (
    CompositionSpec, ImageAsset, LayoutPreset, LayoutSpec, LayerSource, LayerType,
    Region, SceneSpec, TransitionPreset, TransitionSpec, VideoProject, VisualLayer,
    VisualSpec, VisualSpecDecision,
)
from content_creator.services.visual_spec_compiler import expand_transition_preset
from content_creator.services.visual_spec_validator import validate_visual_spec


def project_to_visual_spec(project: VideoProject, stage: Region | None = None, decision: VisualSpecDecision | None = None) -> VisualSpec:
    """Create a deterministic center-stage spec without invoking an LLM."""
    stage = stage or Region(x=0, y=450, width=project.width, height=min(610, project.height), overflow="hidden")
    decisions = {(entry.from_asset_id, entry.to_asset_id): entry for entry in (decision.transitions if decision else [])}
    scenes = []
    transitions = []
    for index, item in enumerate(project.timeline):
        asset = next((candidate for candidate in project.images if candidate.id == item.asset_id), None)
        if asset is None:
            continue
        layer = VisualLayer(id=f"scene-{index}-image", type=LayerType.image, region="stage", source=LayerSource(asset_id=asset.id))
        scenes.append(SceneSpec(id=f"scene-{index}", start_frame=item.start_frame, duration_frames=item.duration_frames, layers=[layer]))
        if index:
            previous = project.timeline[index - 1]
            duration = min(11, item.duration_frames, previous.duration_frames)
            selected = decisions.get((previous.asset_id, item.asset_id))
            transitions.append(TransitionSpec(id=f"transition-{index - 1}-{index}", from_scene=f"scene-{index - 1}", to_scene=f"scene-{index}", start_frame=item.start_frame - duration, duration_frames=duration, preset=selected.preset if selected else TransitionPreset.flash_zoom_blur, params=selected.params if selected else {"incoming_scale": 1.14, "blur_px": 24, "flash_peak": 0.95}))
    duration_frames = max((scene.start_frame + scene.duration_frames for scene in scenes), default=1)
    preset = decision.layout_preset if decision else LayoutPreset.center_stage
    spec = VisualSpec(composition=CompositionSpec(width=project.width, height=project.height, fps=project.fps, duration_frames=duration_frames), layout=LayoutSpec(preset=preset, regions={"stage": stage}), scenes=scenes, transitions=[expand_transition_preset(transition, scenes[index + 1].layers[0].id) for index, transition in enumerate(transitions)])
    return validate_visual_spec(spec)
