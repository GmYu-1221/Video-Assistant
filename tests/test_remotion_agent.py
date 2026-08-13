from pathlib import Path
import json

from content_creator.agents.remotion_agent import _creative_plan_prompt, build_advice, create_animation_plan, load_skill_documents
from content_creator.schemas import DirectorPlan, ScenePlan, Storyboard
from content_creator.services.llm.provider import MockLLMProvider


def _use_fallback(monkeypatch):
    monkeypatch.setattr("content_creator.agents.remotion_agent.get_agent_provider", lambda _: MockLLMProvider())

def test_remotion_agent_reads_official_skill_documents():
    documents = load_skill_documents()
    assert len(documents) == 8
    assert all(Path(document).name == "SKILL.md" for document in documents)


def test_runtime_prompt_includes_motion_and_visual_event_skills_only():
    plan = DirectorPlan.model_validate({"timeline": [{"asset_id": "image-001", "duration_frames": 60, "reason": "opening"}]})
    prompt = json.loads(_creative_plan_prompt(plan))
    assert "Remotion Motion Design" in prompt["remotion_motion_guidelines"]
    assert "Image Animation Guidance" in prompt["remotion_motion_guidelines"]
    assert "Cinematic Motion Guidance" in prompt["remotion_motion_guidelines"]
    assert "Visual Event Architecture" in prompt["project_visual_event_rules"]
    assert "Transition Ownership Rule" in prompt["project_visual_event_rules"]
    assert "camera_push" in prompt["project_visual_event_rules"]
    assert "card_flip_transition" in prompt["project_visual_event_rules"]
    assert "stretch-motion-design" in prompt["remotion_reference_guidelines"]
    assert "blur-transition-design" in prompt["remotion_reference_guidelines"]
    blur_skill = prompt["remotion_reference_guidelines"]["blur-transition-design"]
    assert "# Blur Transition Design" in blur_skill
    assert "gaussian_blur_transition" in blur_skill
    assert "water_ripple_transition" in blur_skill
    assert "Do not generate blur transition from \"cinematic\" alone." in blur_skill
    assert "stretch_reveal" in prompt["remotion_reference_guidelines"]["stretch-motion-design"]
    assert "stretch_transition" in prompt["remotion_reference_guidelines"]["stretch-motion-design"]
    assert "丝滑拉伸" in prompt["remotion_reference_guidelines"]["stretch-motion-design"]
    rules = "\n".join(prompt["rules"])
    assert "default to 10-30 frames (18 frames when no timing is specified)" in rules
    assert "scale 1, rotate 0, translate 0, opacity 1" in rules
    assert "图片丝滑拉伸进入" in rules
    assert "Generate camera_push only when the Director explicitly requests" in rules
    assert "Never infer it from cinematic, dramatic, smooth, premium, entrance, or transition" in rules
    assert "camera_push conflicts with a transition by default" in rules
    assert "Use glass_shatter_transition only for explicit glass" in rules
    assert "Blur is a transition only" in rules
    assert "blur_reveal, blur_effect, or blur_motion" in rules
    assert "unknown, cinematic, dramatic, strong, premium, or impact transitions" in rules
    assert "card_flip_reveal is entrance-only" in rules
    serialized = json.dumps(prompt)
    assert "remotion-engineering" not in serialized

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
    assert animation.type.value == "creative_reveal"
    assert animation.duration_frames == 18
    assert animation.params == {}
    assert animation.implementation == "fallback"


def test_scene_without_creative_intent_does_not_receive_an_animation(monkeypatch):
    _use_fallback(monkeypatch)
    plan = DirectorPlan.model_validate({"timeline": [{"asset_id": "image-001", "duration_frames": 60, "reason": "opening"}]})
    assert create_animation_plan(plan).animations == []
