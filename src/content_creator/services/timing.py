"""Deterministic conversion of Director rhythm weights into exact frame ranges."""
from __future__ import annotations

import math
import unicodedata

from content_creator.schemas import (
    DirectorScene, PresentationPageTiming, PresentationPlan, PresentationScene,
    SceneTiming, TextFieldBudget, TimingPlan, ViralCopyPlan,
)


TYPOGRAPHY_PROFILES = {
    "display": {"font_size_px": 72, "max_lines": 2, "max_units_per_line": 12.0},
    "headline": {"font_size_px": 56, "max_lines": 2, "max_units_per_line": 16.0},
    "body": {"font_size_px": 40, "max_lines": 4, "max_units_per_line": 23.0},
    "label": {"font_size_px": 32, "max_lines": 1, "max_units_per_line": 18.0},
}
VISIBILITY_RATIOS = {"brief": 0.25, "standard": 0.5, "persistent": 0.8}
FIELD_COEFFICIENTS = {"hook": 1.25, "title": 1.15, "body": 1.0, "emphasis": 1.3, "closing": 1.2}
HIERARCHY_COEFFICIENTS = {"primary": 1.2, "secondary": 1.0, "supporting": 0.85}


def compile_timing_plan(
    *,
    total_frames: int,
    fps: int,
    scenes: list[DirectorScene],
    project_width: int = 1080,
    base_reading_units_per_second: float = 10.0,
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
    for scene_index, scene in enumerate(scenes):
        fields = [layout.field for layout in scene.text_layouts]
        if len(fields) != len(set(fields)):
            raise ValueError(f"scene {scene.scene_id} text layout fields must be unique")
        if "hook" in fields and scene_index != 0:
            raise ValueError(f"scene {scene.scene_id} cannot display the global hook outside the first scene")
        if "closing" in fields and scene_index != len(scenes) - 1:
            raise ValueError(f"scene {scene.scene_id} cannot display the global closing outside the last scene")

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
        field_budgets = []
        for layout in scene.text_layouts:
            profile = TYPOGRAPHY_PROFILES[layout.typography_profile]
            min_visible_frames = max(1, math.ceil(scene_frames * VISIBILITY_RATIOS[layout.visibility_profile]))
            spatial_units = profile["max_lines"] * profile["max_units_per_line"]
            coefficient = FIELD_COEFFICIENTS[layout.field] * HIERARCHY_COEFFICIENTS[layout.hierarchy_level]
            temporal_units = min_visible_frames / fps * base_reading_units_per_second / coefficient
            max_total_units = max(0.5, math.floor(min(spatial_units, temporal_units) * 2) / 2)
            field_budgets.append(TextFieldBudget(
                field=layout.field,
                typography_profile=layout.typography_profile,
                visibility_profile=layout.visibility_profile,
                hierarchy_level=layout.hierarchy_level,
                font_size_px=max(1, round(profile["font_size_px"] * project_width / 1080)),
                max_lines=profile["max_lines"],
                max_units_per_line=profile["max_units_per_line"],
                min_visible_frames=min_visible_frames,
                max_total_units=max_total_units,
            ))
        timings.append(SceneTiming(
            scene_id=scene.scene_id, start_frame=cursor, end_frame=end, field_budgets=field_budgets,
        ))
        cursor = end
    return TimingPlan(
        fps=fps,
        duration_frames=total_frames,
        base_reading_units_per_second=base_reading_units_per_second,
        scenes=timings,
    )


def display_width_units(text: str) -> float:
    units = 0.0
    for character in text:
        if character in {"\n", "\r"} or unicodedata.combining(character):
            continue
        units += 1.0 if unicodedata.east_asian_width(character) in {"W", "F", "A"} else 0.5
    return units


def required_display_lines(text: str, max_units_per_line: float) -> int:
    if not text:
        return 0
    return sum(max(1, math.ceil(display_width_units(line) / max_units_per_line)) for line in text.split("\n"))


class PresentationCapacityError(ValueError):
    def __init__(self, scene_id: str, required_frames: int, available_frames: int):
        self.scene_id = scene_id
        self.required_frames = required_frames
        self.available_frames = available_frames
        super().__init__(
            f"scene {scene_id} pages require at least {required_frames} frames, "
            f"but only {available_frames} frames are available"
        )


def compile_presentation_plan(copy: ViralCopyPlan, timing: TimingPlan) -> PresentationPlan:
    if [scene.scene_id for scene in copy.scenes] != [scene.scene_id for scene in timing.scenes]:
        raise ValueError("Copy scene IDs and order must match TimingPlan")
    compiled_scenes = []
    for copy_scene, timing_scene in zip(copy.scenes, timing.scenes):
        budgets = {budget.field: budget for budget in timing_scene.field_budgets}
        required = []
        active_budgets = []
        for page in copy_scene.pages:
            page_budgets = []
            for text in page.texts:
                budget = budgets.get(text.field)
                if budget is None:
                    raise ValueError(f"scene {copy_scene.scene_id} field {text.field} has no Director layout")
                units = display_width_units(text.text)
                lines = required_display_lines(text.text, budget.max_units_per_line)
                if units > budget.max_total_units or lines > budget.max_lines:
                    raise ValueError(
                        f"page {page.page_id} field {text.field} exceeds its per-page display budget"
                    )
                page_budgets.append(budget)
            active_budgets.append(page_budgets)
            required.append(max([budget.min_visible_frames for budget in page_budgets], default=1))
        scene_frames = timing_scene.end_frame - timing_scene.start_frame
        required_total = sum(required)
        if required_total > scene_frames:
            raise PresentationCapacityError(copy_scene.scene_id, required_total, scene_frames)
        surplus = scene_frames - required_total
        quotient, remainder = divmod(surplus, len(copy_scene.pages))
        cursor = timing_scene.start_frame
        pages = []
        for index, (page, minimum, page_budgets) in enumerate(zip(copy_scene.pages, required, active_budgets)):
            page_frames = minimum + quotient + (1 if index < remainder else 0)
            end = cursor + page_frames
            pages.append(PresentationPageTiming(
                page_id=page.page_id, material_id=page.material_id,
                start_frame=cursor, end_frame=end, field_budgets=page_budgets,
            ))
            cursor = end
        compiled_scenes.append(PresentationScene(
            scene_id=copy_scene.scene_id, start_frame=timing_scene.start_frame,
            end_frame=timing_scene.end_frame, pages=pages,
        ))
    return PresentationPlan(
        fps=timing.fps, duration_frames=timing.duration_frames, scenes=compiled_scenes,
    )


def build_reading_load_report(copy: ViralCopyPlan, timing: TimingPlan, presentation: PresentationPlan | None = None) -> dict:
    scenes = []
    presentation_by_scene = {scene.scene_id: scene for scene in presentation.scenes} if presentation else {}
    for copy_scene, timing_scene in zip(copy.scenes, timing.scenes):
        budget_by_field = {budget.field: budget for budget in timing_scene.field_budgets}
        compiled_pages = presentation_by_scene.get(copy_scene.scene_id)
        pages = []
        for page_index, page in enumerate(copy_scene.pages):
            fields = []
            for text in page.texts:
                budget = budget_by_field[text.field]
                units = display_width_units(text.text)
                lines = required_display_lines(text.text, budget.max_units_per_line)
                fields.append({
                    "field": text.field, "display_units": units, "required_lines": lines,
                    "max_total_units": budget.max_total_units, "max_lines": budget.max_lines,
                    "max_units_per_line": budget.max_units_per_line, "font_size_px": budget.font_size_px,
                    "min_visible_frames": budget.min_visible_frames,
                    "within_budget": units <= budget.max_total_units and lines <= budget.max_lines,
                })
            compiled = compiled_pages.pages[page_index] if compiled_pages else None
            pages.append({
                "page_id": page.page_id, "material_id": page.material_id,
                "start_frame": compiled.start_frame if compiled else None,
                "end_frame": compiled.end_frame if compiled else None,
                "fields": fields,
            })
        scenes.append({"scene_id": timing_scene.scene_id, "pages": pages})
    return {"base_reading_units_per_second": timing.base_reading_units_per_second, "scenes": scenes}
