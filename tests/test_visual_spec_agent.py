import json

from content_creator.agents.remotion_agent import create_visual_spec_decision
from content_creator.schemas import DirectorPlan


class DecisionLLM:
    model_name = "test"
    def complete_json(self, _prompt):
        return json.dumps({"layout_preset": "center_stage", "transitions": [{"from_asset_id": "a", "to_asset_id": "b", "preset": "flash_zoom_blur", "params": {"blur_px": 24}}]})


def test_visual_spec_agent_only_accepts_adjacent_boundaries():
    plan = DirectorPlan.model_validate({"timeline": [{"asset_id": "a", "duration_frames": 60}, {"asset_id": "b", "duration_frames": 60}]})
    decision = create_visual_spec_decision(plan, provider=DecisionLLM())
    assert decision.transitions[0].preset.value == "flash_zoom_blur"
