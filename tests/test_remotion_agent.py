from pathlib import Path
from content_creator.agents.remotion_agent import build_advice, create_animation_plan, load_skill_documents
from content_creator.schemas import DirectorPlan, ScenePlan, Storyboard
from content_creator.services.llm.provider import MockLLMProvider


def _use_fallback(monkeypatch):
    monkeypatch.setattr("content_creator.agents.remotion_agent.get_agent_provider", lambda _: MockLLMProvider())

def test_remotion_agent_reads_official_skill_documents():
    documents = load_skill_documents()
    assert len(documents) == 4
    assert all(Path(document).name == "SKILL.md" for document in documents)

def test_remotion_advice_enforces_existing_rendering_rules():
    advice = build_advice({"storyboard": Storyboard(scenes=[ScenePlan(scene_id="001", asset_id="image-001", duration_frames=60)])})
    assert advice.image_fit == "contain"
    assert advice.motion_default == "static"
    assert advice.transition_registry_required


def test_creative_intent_maps_to_effect_plan(monkeypatch):
    _use_fallback(monkeypatch)
    plan = DirectorPlan.model_validate({"timeline": [{"asset_id": "image-001", "duration_frames": 60, "reason": "flip", "creative_intent": {"description": "Image rotates from back to front", "movement": "Y rotation", "effects": ["motion blur"]}}]})
    animation = create_animation_plan(plan).animations[0]
    assert animation.type.value == "creative_reveal"
    assert animation.component == "CreativeReveal"
    assert animation.implementation == "fallback"


def test_particle_flip_creative_intent_has_executable_particle_parameters(monkeypatch):
    _use_fallback(monkeypatch)
    plan = DirectorPlan.model_validate({"timeline": [{"asset_id": "image-001", "duration_frames": 60, "reason": "opening", "creative_intent": {"description": "Image flips upward from bottom with particles", "effects": ["particle dissolve"]}}]})
    animation = create_animation_plan(plan).animations[0]
    assert animation.type.value == "particle_flip_reveal"
    assert animation.duration_frames == 24
    assert animation.params == {"particle_density": 120, "rotation_axis": "Y", "motion_blur": True, "perspective": 800, "energy": 0.5}
    assert animation.implementation == "fallback"


def test_scene_without_creative_intent_does_not_receive_an_animation(monkeypatch):
    _use_fallback(monkeypatch)
    plan = DirectorPlan.model_validate({"timeline": [{"asset_id": "image-001", "duration_frames": 60, "reason": "opening"}]})
    assert create_animation_plan(plan).animations == []
