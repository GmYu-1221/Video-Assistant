from pathlib import Path
from content_creator.agents.remotion_agent import build_advice, create_animation_plan, load_skill_documents
from content_creator.schemas import AnimationIntent, DirectorPlan, ScenePlan, Storyboard

def test_remotion_agent_reads_official_skill_documents():
    documents = load_skill_documents()
    assert len(documents) == 4
    assert all(Path(document).name == "SKILL.md" for document in documents)

def test_remotion_advice_enforces_existing_rendering_rules():
    advice = build_advice({"storyboard": Storyboard(scenes=[ScenePlan(scene_id="001", asset_id="image-001", duration_frames=60)])})
    assert advice.image_fit == "contain"
    assert advice.motion_default == "static"
    assert advice.transition_registry_required


def test_animation_intent_maps_to_custom_effect_plan():
    plan = DirectorPlan.model_validate({"timeline": [{"asset_id": "image-001", "duration_frames": 60, "reason": "flip", "animation_intent": {"type": "3d_card_flip", "duration_frames": 18}}]})
    animation = create_animation_plan(plan).animations[0]
    assert animation.effect.value == "card_flip_reveal"
    assert animation.component == "CardFlipReveal"
    assert animation.implementation == "custom"
    assert animation.props == {"perspective": 800, "rotateY": 180}


def test_unknown_animation_intent_has_safe_fallback():
    plan = DirectorPlan.model_validate({"timeline": [{"asset_id": "image-001", "duration_frames": 60, "reason": "unknown", "animation_intent": {"type": "laser_portal", "duration_frames": 18}}]})
    animation = create_animation_plan(plan).animations[0]
    assert animation.implementation == "fallback"
    assert animation.component == "FadeFallback"
