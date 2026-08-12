import json
import pytest
from content_creator.schemas import TransitionConfig, TransitionPlan, TransitionPlanItem, TransitionPolicy, TransitionType
from content_creator.services.timeline.slideshow_builder import _choose_types


def test_random_policy_avoids_repeat():
    policy = TransitionPolicy(mode="random", allowed=[TransitionType.fade, TransitionType.slide_left], seed=3)
    chosen = _choose_types(8, policy)
    assert all(a != b for a, b in zip(chosen, chosen[1:]))


def test_weighted_policy_and_serialization():
    config = TransitionConfig(type=TransitionType.zoom_blur, duration_frames=18, direction="center", intensity=0.7)
    restored = TransitionConfig.model_validate(json.loads(config.model_dump_json()))
    assert restored == config


def test_invalid_transition_rejected():
    with pytest.raises(ValueError):
        TransitionConfig(type="not-a-transition")


def test_transition_plan_round_trip():
    plan = TransitionPlan(transitions=[TransitionPlanItem(index=0, transition=TransitionConfig(type=TransitionType.fade))])
    assert TransitionPlan.model_validate_json(plan.model_dump_json()) == plan
