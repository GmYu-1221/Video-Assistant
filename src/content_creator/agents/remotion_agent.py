"""Remotion Creative Agent: validated director intents -> supported effect plans."""

from __future__ import annotations

from pathlib import Path

from content_creator.schemas import (
    AnimationEffect,
    AnimationEffectType,
    AnimationPlan,
    DirectorPlan,
    RemotionAdvice,
)

_SKILL_NAMES = ("remotion-best-practices", "remotion-docs", "remotion-markup", "remotion-render")

_INTENT_MAP = {
    "3d_card_flip": (AnimationEffectType.card_flip_reveal, "CardFlipReveal", {"perspective": 800, "rotateY": 180}),
    "camera_push": (AnimationEffectType.camera_push, "CameraPush", {"translatePercent": 4}),
    "glitch": (AnimationEffectType.glitch_reveal, "GlitchReveal", {"rgbOffset": 8}),
    "glitch_reveal": (AnimationEffectType.glitch_reveal, "GlitchReveal", {"rgbOffset": 8}),
    "light_leak": (AnimationEffectType.light_leak, "LightLeak", {"intensity": 0.75}),
}


def _skill_root() -> Path:
    return Path(__file__).resolve().parents[3] / ".agents" / "skills"


def load_skill_documents() -> tuple[str, ...]:
    root = _skill_root()
    documents = tuple(str(root / name / "SKILL.md") for name in _SKILL_NAMES if (root / name / "SKILL.md").is_file())
    if not documents:
        raise RuntimeError("official Remotion skills are not installed under .agents/skills")
    return documents


def create_animation_plan(plan: DirectorPlan) -> AnimationPlan:
    """Map known intent names to Registry effects and preserve unknown intent safely."""
    animations: list[AnimationEffect] = []
    for item in plan.timeline:
        intent = item.animation_intent
        if not intent:
            continue
        mapping = _INTENT_MAP.get(intent.type)
        if mapping is None:
            animations.append(AnimationEffect(asset_id=item.asset_id, effect=AnimationEffectType.none, component="FadeFallback", implementation="fallback", duration_frames=min(intent.duration_frames, item.duration_frames), props={"intent_type": intent.type}, fallback=AnimationEffectType.none))
            continue
        effect, component, props = mapping
        animations.append(AnimationEffect(asset_id=item.asset_id, effect=effect, component=component, implementation="custom", duration_frames=min(intent.duration_frames, item.duration_frames), props=props, fallback=AnimationEffectType.none))
    return AnimationPlan(animations=animations)


def build_advice(state: dict) -> RemotionAdvice:
    storyboard = state["storyboard"]
    if any(scene.motion.type != "static" for scene in storyboard.scenes):
        raise ValueError("Remotion Agent requires static motion unless explicitly approved by a future policy")
    return RemotionAdvice(skill_documents=load_skill_documents())


def remotion_node(state: dict) -> dict:
    advice = build_advice(state)
    plan = state.get("director_plan")
    animation_plan = create_animation_plan(plan) if plan else AnimationPlan()
    return {"remotion_advice": advice, "animation_plan": animation_plan}
