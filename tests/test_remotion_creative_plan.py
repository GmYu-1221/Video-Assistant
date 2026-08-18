import json
import logging

from content_creator.agents.remotion_agent import create_remotion_creative_plan
from content_creator.schemas import DirectorPlan


def plan(**first):
    return DirectorPlan.model_validate({"timeline": [
        {"asset_id": "image-001", "duration_frames": 60, "reason": "first", **first},
        {"asset_id": "image-002", "duration_frames": 60, "reason": "second"},
    ]})


class Provider:
    model_name = "test-remotion"

    def __init__(self, payload):
        self.payload = payload

    def complete_json(self, _prompt):
        return json.dumps(self.payload)


def test_empty_registry_drops_legacy_transition_event_and_keeps_entrance(caplog):
    provider = Provider({"plans": [{"scene_id": "image-001", "visual_events": [
        {"type": "legacy_transition", "phase": "transition", "start_frame": 30, "duration_frames": 30, "source_asset_id": "image-001", "target_asset_id": "image-002", "params": {}},
        {"type": "creative_reveal", "phase": "entrance", "start_frame": 0, "duration_frames": 18, "params": {}},
    ]}]})
    with caplog.at_level(logging.WARNING):
        result = create_remotion_creative_plan(plan(creative_intent={"description": "图片进入"}, transition_intent={"description": "切换"}), provider=provider)
    assert [event.type for event in result.plans[0].visual_events] == ["creative_reveal"]
    assert "Dropped event" in caplog.text


def test_invalid_transition_never_creates_a_fallback_transition():
    provider = Provider({"plans": [{"scene_id": "image-001", "visual_events": [
        {"type": "template_transition", "phase": "transition", "start_frame": 30, "duration_frames": 30, "source_asset_id": "image-001", "target_asset_id": "image-002", "params": {}},
    ]}]})
    result = create_remotion_creative_plan(plan(transition_intent={"description": "切换"}), provider=provider)
    assert result.plans[0].visual_events == []


def test_fallback_plan_contains_only_animation_events(monkeypatch):
    monkeypatch.setattr("content_creator.agents.remotion_agent.get_agent_provider", lambda _: type("Mock", (), {"model_name": "mock"})())
    result = create_remotion_creative_plan(plan(creative_intent={"description": "图片进入"}, transition_intent={"description": "切换"}))
    assert [event.phase for event in result.plans[0].visual_events] == ["entrance"]
    assert result.plans[0].visual_events[0].type == "creative_reveal"


def test_valid_entrance_event_remains_supported():
    provider = Provider({"plans": [{"scene_id": "image-001", "visual_events": [
        {"type": "stretch_reveal", "phase": "entrance", "start_frame": 0, "duration_frames": 18, "params": {"intensity": 0.7}},
    ]}]})
    result = create_remotion_creative_plan(plan(creative_intent={"description": "图片进入"}), provider=provider)
    assert result.plans[0].visual_events[0].type == "stretch_reveal"


def test_registered_qwen3_8_transition_event_is_validated():
    provider = Provider({"plans": [{"scene_id": "image-001", "visual_events": [
        {
            "type": "template_transition",
            "phase": "transition",
            "start_frame": 30,
            "duration_frames": 24,
            "source_asset_id": "image-001",
            "target_asset_id": "image-002",
            "params": {
                "template_id": "qwen3_8",
                "parameters": {
                    "blur_strength": 0.8,
                    "float_distance": 0.55,
                    "recovery_speed": 0.7,
                    "opacity_start": 0.88,
                },
            },
        },
    ]}]})
    result = create_remotion_creative_plan(
        plan(transition_intent={"description": "柔和高级图片转场"}),
        provider=provider,
    )
    event = result.plans[0].visual_events[0]
    assert event.type == "template_transition"
    assert event.params["template_id"] == "qwen3_8"
