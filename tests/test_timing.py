import pytest
from pydantic import ValidationError

from content_creator.schemas import DirectorPlan, DirectorScene
from content_creator.services.timing import compile_timing_plan


def scene(index: int, weight: float = 1) -> DirectorScene:
    return DirectorScene(
        scene_id=f"scene-{index}", material_ids=[f"material-{index}"], duration_weight=weight,
        image_intent="主体", camera_intent="静止", transition_intent="切换", information_hierarchy="标题正文",
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
    assert all(item.end_frame > item.start_frame and item.text_budget >= 1 for item in first.scenes)


def test_equal_remainders_are_awarded_in_scene_order():
    timing = compile_timing_plan(total_frames=5, fps=30, scenes=[scene(1), scene(2), scene(3)])
    assert [item.end_frame - item.start_frame for item in timing.scenes] == [2, 2, 1]
