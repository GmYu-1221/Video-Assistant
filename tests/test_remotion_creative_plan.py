import json

from content_creator.agents.remotion_agent import create_remotion_creative_plan
from content_creator.schemas import DirectorPlan


class UnifiedLLM:
    model_name = "claude-remotion"

    def __init__(self):
        self.calls = 0

    def complete_json(self, _prompt: str) -> str:
        self.calls += 1
        return json.dumps({"plans": [{"scene_id": "image-001", "visual_events": [
            {"type": "drop_reveal_elastic", "phase": "entrance", "start_frame": 0, "duration_frames": 24, "params": {"direction": "top"}},
            {"type": "glass_shatter_transition", "phase": "transition", "start_frame": 30, "duration_frames": 30, "source_asset_id": "image-001", "target_asset_id": "image-002", "params": {"fragment_count": 72}},
        ]}]})


def test_unified_remotion_plan_uses_one_llm_call(monkeypatch):
    provider = UnifiedLLM()
    monkeypatch.setattr("content_creator.agents.remotion_agent.get_agent_provider", lambda _: provider)
    plan = DirectorPlan.model_validate({"timeline": [
        {"asset_id": "image-001", "duration_frames": 60, "reason": "first", "creative_intent": {"description": "drop from above"}, "transition_intent": {"description": "glass shatter"}},
        {"asset_id": "image-002", "duration_frames": 60, "reason": "second"},
    ]})
    result = create_remotion_creative_plan(plan)
    assert provider.calls == 1
    assert [event.type for event in result.plans[0].visual_events] == ["drop_reveal_elastic", "glass_shatter_transition"]
    transition = result.plans[0].visual_events[1]
    assert transition.source_asset_id == "image-001"
    assert transition.target_asset_id == "image-002"


class ConflictingLLM(UnifiedLLM):
    def complete_json(self, _prompt: str) -> str:
        self.calls += 1
        return json.dumps({"plans": [
            {"scene_id": "image-001", "visual_events": [{"type": "glass_shatter_transition", "phase": "transition", "start_frame": 30, "duration_frames": 30, "source_asset_id": "image-001", "target_asset_id": "image-002", "params": {"fragment_count": 64}}]},
            {"scene_id": "image-002", "visual_events": [{"type": "creative_reveal", "phase": "entrance", "start_frame": 0, "duration_frames": 18, "params": {}}]},
        ]})


def test_transition_removes_target_entrance(monkeypatch):
    provider = ConflictingLLM()
    monkeypatch.setattr("content_creator.agents.remotion_agent.get_agent_provider", lambda _: provider)
    plan = DirectorPlan.model_validate({"timeline": [
        {"asset_id": "image-001", "duration_frames": 60, "reason": "first", "transition_intent": {"description": "glass shatter into image two"}},
        {"asset_id": "image-002", "duration_frames": 60, "reason": "second", "creative_intent": {"description": "appear behind fragments"}},
    ]})
    result = create_remotion_creative_plan(plan)
    assert result.plans[0].visual_events[0].type == "glass_shatter_transition"
    assert result.plans[1].visual_events == []
