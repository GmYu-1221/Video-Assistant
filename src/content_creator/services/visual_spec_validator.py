"""Semantic checks performed after schema validation and before rendering."""
from __future__ import annotations

from content_creator.schemas import VisualSpec


def validate_visual_spec(spec: VisualSpec) -> VisualSpec:
    ordered = sorted(spec.scenes, key=lambda scene: scene.start_frame)
    if len({scene.id for scene in ordered}) != len(ordered):
        raise ValueError("Visual Spec scene ids must be unique")
    for index, transition in enumerate(spec.transitions):
        source = next(scene for scene in ordered if scene.id == transition.from_scene)
        target = next(scene for scene in ordered if scene.id == transition.to_scene)
        source_index = ordered.index(source)
        if source_index + 1 >= len(ordered) or ordered[source_index + 1].id != target.id:
            raise ValueError("Visual Spec transitions must join adjacent scenes")
        if transition.start_frame < target.start_frame - transition.duration_frames or transition.start_frame >= target.start_frame:
            raise ValueError("Visual Spec transition must end at its target scene boundary")
        if transition.duration_frames > min(source.duration_frames, target.duration_frames):
            raise ValueError("Visual Spec transition exceeds adjacent scene duration")
    return spec
