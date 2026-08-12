from content_creator.agents.director_chat import merge_director_plan_patch
from content_creator.agents.remotion_agent import create_animation_plan
from content_creator.schemas import DirectorPlan, DirectorPlanPatch
from content_creator.services.llm.provider import MockLLMProvider


def test_creative_intent_is_implementation_neutral_until_remotion_agent():
    plan = DirectorPlan.model_validate({"timeline": [{"asset_id": "image-001", "duration_frames": 60, "reason": "opening"}]})
    patch = DirectorPlanPatch.model_validate({"operations": [{"scene_id": "image-001", "changes": {"creative_intent": {"description": "Image drops from the sky and expands elastically", "movement": "vertical drop with spring settle", "effects": ["temporary stretch"], "energy": 0.8}}}]})
    updated = merge_director_plan_patch(plan, patch)
    intent = updated.timeline[0].creative_intent
    assert intent is not None
    assert "drops" in intent.description
    assert "stretch_reveal" not in intent.description


def test_creative_intent_reaches_remotion_agent_without_fade_fallback(monkeypatch):
    monkeypatch.setattr("content_creator.agents.remotion_agent.get_agent_provider", lambda _: MockLLMProvider())
    plan = DirectorPlan.model_validate({"timeline": [{"asset_id": "image-001", "duration_frames": 60, "reason": "opening", "creative_intent": {"description": "Image drops from the sky and expands elastically", "movement": "translateY then spring", "effects": ["temporary stretch"], "energy": 0.8}}]})
    animation = create_animation_plan(plan, mode="creative").animations[0]
    assert animation.implementation == "fallback"
    assert animation.effect.value != "none"
