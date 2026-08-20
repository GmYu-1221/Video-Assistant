import pytest
from pydantic import ValidationError

from content_creator.schemas import (
    CopyPage, CopyPageText, CopyScene, DirectorPlan, DirectorScene, DirectorTextLayout, SourceReference,
    ViralCopyPlan,
)
from content_creator.services.timing import (
    PresentationCapacityError, build_reading_load_report, compile_presentation_plan,
    compile_timing_plan, display_width_units,
)


def layout(field="title", hierarchy="primary") -> DirectorTextLayout:
    return DirectorTextLayout(
        field=field, typography_profile="headline", visibility_profile="standard",
        hierarchy_level=hierarchy,
    )


def scene(index: int, weight: float = 1) -> DirectorScene:
    return DirectorScene(
        scene_id=f"scene-{index}", material_ids=[f"material-{index}"], duration_weight=weight,
        image_intent="主体", camera_intent="静止", transition_intent="切换", information_hierarchy="标题正文",
        text_layouts=[layout()],
    )


def director(duration_seconds) -> DirectorPlan:
    return DirectorPlan(
        duration_seconds=duration_seconds, duration_reason="依据 beat 和素材数量决定", safe_area="安全区",
        background_atmosphere="深色", typography_hierarchy="标题正文", alignment_tendency="居中", rhythm="快",
        scenes=[scene(1)],
    )


@pytest.mark.parametrize(("seconds", "frames"), [(15, 450), (90, 2700)])
def test_director_duration_bounds_are_integer_seconds_and_frames_are_derived(seconds, frames):
    plan = director(seconds)
    assert plan.duration_frames == frames
    assert "duration_frames" not in DirectorPlan.model_json_schema()["properties"]


@pytest.mark.parametrize("seconds", [14, 91, 15.5])
def test_director_rejects_out_of_range_or_non_integer_duration(seconds):
    with pytest.raises(ValidationError):
        director(seconds)


def test_director_rejects_model_supplied_duration_frames():
    payload = director(15).model_dump(exclude={"duration_frames"})
    payload["duration_frames"] = 999
    with pytest.raises(ValidationError, match="duration_frames"):
        DirectorPlan.model_validate(payload)


@pytest.mark.parametrize("weights", [[1], [1] * 12, [0.1, 0.2, 0.7], [1, 1, 1]])
def test_compiler_is_stable_contiguous_and_exact(weights):
    scenes = [scene(index, weight) for index, weight in enumerate(weights)]
    first = compile_timing_plan(total_frames=451, fps=30, scenes=scenes)
    second = compile_timing_plan(total_frames=451, fps=30, scenes=scenes)
    assert first == second
    assert first.scenes[0].start_frame == 0
    assert first.scenes[-1].end_frame == 451
    assert all(left.end_frame == right.start_frame for left, right in zip(first.scenes, first.scenes[1:]))
    assert all(item.end_frame > item.start_frame and item.field_budgets for item in first.scenes)


def test_equal_remainders_are_awarded_in_scene_order():
    timing = compile_timing_plan(total_frames=5, fps=30, scenes=[scene(1), scene(2), scene(3)])
    assert [item.end_frame - item.start_frame for item in timing.scenes] == [2, 2, 1]


def test_higher_hierarchy_coefficient_requires_more_concise_copy():
    primary_scene = scene(1)
    supporting_scene = scene(2)
    primary_scene.text_layouts = [layout(hierarchy="primary")]
    supporting_scene.text_layouts = [layout(hierarchy="supporting")]
    timing = compile_timing_plan(total_frames=120, fps=30, scenes=[primary_scene, supporting_scene])
    assert timing.scenes[0].field_budgets[0].max_total_units < timing.scenes[1].field_budgets[0].max_total_units


def test_higher_field_coefficient_requires_more_concise_copy():
    title_scene = scene(1)
    emphasis_scene = scene(2)
    title_scene.text_layouts = [layout(field="title", hierarchy="secondary")]
    emphasis_scene.text_layouts = [layout(field="emphasis", hierarchy="secondary")]
    timing = compile_timing_plan(total_frames=120, fps=30, scenes=[title_scene, emphasis_scene])
    assert timing.scenes[1].field_budgets[0].max_total_units < timing.scenes[0].field_budgets[0].max_total_units


def test_base_rate_is_a_reading_load_heuristic_and_not_a_speaking_rate():
    timing = compile_timing_plan(total_frames=450, fps=30, scenes=[scene(1)])
    payload = timing.model_dump()
    assert payload["base_reading_units_per_second"] == 10
    assert "speaking_chars_per_second" not in payload
    assert "screen_reading_units_per_second" not in payload


def test_empty_fields_generate_neither_field_budgets_nor_reading_load():
    ref = SourceReference(source_id="source-001", paragraph_index=0)
    copy = ViralCopyPlan(
        final_title="封面标题", scenes=[CopyScene(scene_id="scene-1", pages=[CopyPage(
            page_id="scene-1-page-001", material_id="material-1",
            texts=[CopyPageText(field="hook", text="钩子")], source_references=[ref],
        )])],
    )
    director_scene = scene(1)
    director_scene.text_layouts = [layout(field="hook")]
    timing = compile_timing_plan(total_frames=450, fps=30, scenes=[director_scene])
    report = build_reading_load_report(copy, timing)
    assert [budget.field for budget in timing.scenes[0].field_budgets] == ["hook"]
    assert [field["field"] for field in report["scenes"][0]["pages"][0]["fields"]] == ["hook"]


def test_text_free_scene_has_no_field_budgets():
    visual_only = scene(1)
    visual_only.text_layouts = []
    timing = compile_timing_plan(total_frames=450, fps=30, scenes=[visual_only])
    assert timing.scenes[0].field_budgets == []


def test_display_width_units_use_cjk_full_units_and_ascii_half_units():
    assert display_width_units("中文AB") == 3


def test_presentation_compiler_allocates_contiguous_pages_and_reuses_material():
    ref = SourceReference(source_id="source-001", paragraph_index=0)
    director_scene = scene(1)
    director_scene.text_layouts = [layout(field="body", hierarchy="secondary")]
    timing = compile_timing_plan(total_frames=300, fps=30, scenes=[director_scene])
    copy = ViralCopyPlan(final_title="封面标题", scenes=[CopyScene(scene_id="scene-1", pages=[
        CopyPage(page_id="scene-1-page-001", material_id="material-1", texts=[CopyPageText(field="body", text="第一段")], source_references=[ref]),
        CopyPage(page_id="scene-1-page-002", material_id="material-1", texts=[CopyPageText(field="body", text="第二段")], source_references=[ref]),
    ])])
    presentation = compile_presentation_plan(copy, timing)
    pages = presentation.scenes[0].pages
    assert pages[0].start_frame == 0
    assert pages[0].end_frame == pages[1].start_frame
    assert pages[-1].end_frame == 300
    assert [page.material_id for page in pages] == ["material-1", "material-1"]


def test_presentation_compiler_requests_scene_split_when_page_minima_do_not_fit():
    ref = SourceReference(source_id="source-001", paragraph_index=0)
    director_scene = scene(1)
    director_scene.text_layouts = [layout(field="body", hierarchy="secondary")]
    timing = compile_timing_plan(total_frames=120, fps=30, scenes=[director_scene])
    pages = [CopyPage(
        page_id=f"scene-1-page-{index:03d}", material_id="material-1",
        texts=[CopyPageText(field="body", text=f"第{index}段")], source_references=[ref],
    ) for index in range(1, 4)]
    copy = ViralCopyPlan(final_title="封面标题", scenes=[CopyScene(scene_id="scene-1", pages=pages)])
    with pytest.raises(PresentationCapacityError, match="require at least"):
        compile_presentation_plan(copy, timing)
