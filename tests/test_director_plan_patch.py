import json

import pytest

from content_creator.agents.director_chat import merge_director_plan_patch
from content_creator.schemas import DirectorPlan
from content_creator.services.llm.validator import validate_director_plan_patch_json


def _plan() -> DirectorPlan:
    return DirectorPlan.model_validate({"timeline": [
        {"asset_id": "image-001", "duration_frames": 60, "transition": {"type": "fade", "duration_frames": 8}, "reason": "opening"},
        {"asset_id": "image-002", "duration_frames": 90, "transition": {"type": "push", "duration_frames": 6}, "reason": "middle"},
        {"asset_id": "image-003", "duration_frames": 75, "transition": {"type": "whip", "duration_frames": 5}, "reason": "climax"},
    ]})


def _patch(payload: dict):
    return validate_director_plan_patch_json(json.dumps(payload), ["image-001", "image-002", "image-003"])


def test_patch_updates_only_creative_intent():
    plan = _plan()
    updated = merge_director_plan_patch(plan, _patch({"operations": [{"scene_id": "image-001", "changes": {"creative_intent": {"description": "Image flips upward from the bottom", "movement": "vertical rotation", "camera": "subtle perspective", "effects": ["motion blur"], "timing": "cinematic entrance", "energy": 0.8, "emotion": "dramatic", "style": "cinematic"}}}]}))
    scene = updated.timeline[0]
    assert scene.creative_intent is not None
    assert scene.creative_intent.scene_id == "image-001"
    assert scene.duration_frames == 60
    assert scene.transition.type.value == "fade"
    assert updated.timeline[1].model_dump() == plan.timeline[1].model_dump()


def test_particle_entrance_patch_from_plain_json_is_applied():
    plan = _plan()
    updated = merge_director_plan_patch(plan, _patch({"operations": [{"scene_id": "image-001", "changes": {"creative_intent": {"description": "Image enters through a cinematic particle assembly", "movement": "upward reveal", "camera": "subtle perspective push", "effects": ["particle dissolve", "motion blur"], "timing": "fast entrance", "energy": 0.8, "emotion": "dramatic", "style": "cinematic"}}}]}))
    assert updated.timeline[0].creative_intent.description == "Image enters through a cinematic particle assembly"
    assert updated.timeline[0].creative_intent.effects == ["particle dissolve", "motion blur"]


def test_patch_extracts_a_single_markdown_json_fence():
    patch = validate_director_plan_patch_json("""```json
{"operations": [{"scene_id": "image-001", "changes": {"duration_frames": 72}}]}
```""", ["image-001", "image-002", "image-003"])
    assert patch.operations[0].changes.duration_frames == 72


def test_patch_rejects_complete_director_plan_without_mutating_plan():
    plan = _plan()
    before = plan.model_dump()
    with pytest.raises(ValueError, match="not a complete DirectorPlan"):
        validate_director_plan_patch_json(json.dumps(plan.model_dump()), ["image-001", "image-002", "image-003"])
    assert plan.model_dump() == before


def test_patch_updates_duration_only():
    plan = _plan()
    updated = merge_director_plan_patch(plan, _patch({"operations": [{"scene_id": "image-003", "changes": {"duration_frames": 113}}]}))
    assert updated.timeline[2].duration_frames == 113
    assert updated.timeline[2].transition == plan.timeline[2].transition


def test_patch_updates_transition_only():
    plan = _plan()
    updated = merge_director_plan_patch(plan, _patch({"operations": [{"scene_id": "image-002", "changes": {"transition": {"type": "whip", "duration_frames": 5}}}]}))
    assert updated.timeline[1].transition.type.value == "whip"
    assert updated.timeline[1].duration_frames == 90


def test_patch_updates_emotion_and_timing_only():
    plan = _plan()
    updated = merge_director_plan_patch(plan, _patch({"operations": [{"scene_id": "image-001", "changes": {"emotion": "reflective", "timing": "slow settle"}}]}))
    assert updated.timeline[0].reason == "reflective"
    assert updated.timeline[0].timing == "slow settle"
    assert updated.timeline[0].duration_frames == 60


def test_patch_rejects_unknown_scene_id():
    with pytest.raises(ValueError, match="Valid asset_ids: image-001, image-002, image-003"):
        _patch({"operations": [{"scene_id": "Scene01", "changes": {"duration_frames": 30}}]})


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"operations": [{"scene_id": "image-001", "changes": {}}]}, "changes cannot be empty"),
        ({"operations": [{"scene_id": "image-001", "changes": {"creative_intent": {"movement": "upward"}}}]}, "creative_intent.description"),
        ({"operations": [{"scene_id": "image-001", "changes": {"transition": {"type": "not-real", "duration_frames": 0}}}]}, "Invalid transition"),
    ],
)
def test_patch_reports_field_level_validation_errors(payload, message):
    with pytest.raises(ValueError, match=message):
        _patch(payload)
