"""Deterministic conversion of Director rhythm weights into exact frame ranges."""
from __future__ import annotations

import math

from content_creator.schemas import DirectorScene, SceneTiming, TimingPlan


def compile_timing_plan(
    *,
    total_frames: int,
    fps: int,
    scenes: list[DirectorScene],
    speaking_chars_per_second: float = 7.0,
) -> TimingPlan:
    if not scenes:
        raise ValueError("Director must provide at least one scene")
    if total_frames < len(scenes):
        raise ValueError(f"total_frames={total_frames} cannot give {len(scenes)} scenes at least one frame each")
    ids = [scene.scene_id for scene in scenes]
    if len(ids) != len(set(ids)):
        raise ValueError("Director scene IDs must be unique")
    if any(scene.duration_weight <= 0 for scene in scenes):
        raise ValueError("Director scene duration weights must be positive")

    remaining = total_frames - len(scenes)
    weight_sum = sum(scene.duration_weight for scene in scenes)
    quotas = [remaining * scene.duration_weight / weight_sum for scene in scenes]
    extras = [math.floor(quota) for quota in quotas]
    leftover = remaining - sum(extras)
    # Stable largest-remainder allocation: scene order breaks equal remainders.
    order = sorted(range(len(scenes)), key=lambda index: (-(quotas[index] - extras[index]), index))
    for index in order[:leftover]:
        extras[index] += 1

    timings: list[SceneTiming] = []
    cursor = 0
    for scene, extra in zip(scenes, extras):
        scene_frames = 1 + extra
        end = cursor + scene_frames
        budget = max(1, math.floor(scene_frames / fps * speaking_chars_per_second))
        timings.append(SceneTiming(scene_id=scene.scene_id, start_frame=cursor, end_frame=end, text_budget=budget))
        cursor = end
    return TimingPlan(
        fps=fps,
        duration_frames=total_frames,
        speaking_chars_per_second=speaking_chars_per_second,
        scenes=timings,
    )
