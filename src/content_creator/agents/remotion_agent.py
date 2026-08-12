"""Remotion Creative Agent: validated director intents -> supported effect plans."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from content_creator.schemas import (
    AnimationEffect,
    AnimationEffectType,
    AnimationPlan,
    DirectorPlan,
    RemotionAdvice,
    TransitionEffectPlan,
    TransitionEffectPlanItem,
    TransitionEffectType,
)
from content_creator.services.llm.router import get_agent_provider

_SKILL_NAMES = ("remotion-best-practices", "remotion-docs", "remotion-markup", "remotion-render")
_EFFECT_COMPONENTS = {
    AnimationEffectType.card_flip_reveal: "CardFlipReveal",
    AnimationEffectType.camera_push: "CameraPush",
    AnimationEffectType.glitch_reveal: "GlitchReveal",
    AnimationEffectType.light_leak: "LightLeak",
    AnimationEffectType.stretch_reveal: "StretchReveal",
    AnimationEffectType.drop_reveal_elastic: "DropRevealElastic",
    AnimationEffectType.particle_flip_reveal: "ParticleFlipReveal",
    AnimationEffectType.creative_reveal: "CreativeReveal",
}
_TRANSITION_EFFECT_CAPABILITIES = {
    TransitionEffectType.glass_shatter_transition: {
        "description": "The outgoing image fractures into cinematic glass-like fragments while the incoming image is revealed behind it.",
        "params": {
            "fragment_count": {"type": "number", "minimum": 12, "maximum": 96, "description": "Number of visible fragment cells."},
            "impact_origin": {"type": "enum", "values": ["center", "left", "right", "top", "bottom"], "description": "Where the glass fracture begins."},
            "motion_blur": {"type": "boolean", "description": "Enable a motion-blur approximation while shards move."},
        },
    },
}
logger = logging.getLogger(__name__)
_SECRET = re.compile(r"(?i)(?:authorization\s*:\s*(?:bearer\s+)?|bearer\s+|api[_-]?key\s*[:=]\s*|token\s*[:=]\s*|password\s*[:=]\s*)[^\s,;]+")


class InvalidAnimationResponse(ValueError):
    """Raised only when no JSON object can be recovered from an LLM response."""

def _skill_root() -> Path:
    return Path(__file__).resolve().parents[3] / ".agents" / "skills"


def load_skill_documents() -> tuple[str, ...]:
    root = _skill_root()
    documents = tuple(str(root / name / "SKILL.md") for name in _SKILL_NAMES if (root / name / "SKILL.md").is_file())
    if len(documents) != len(_SKILL_NAMES):
        raise RuntimeError("Remotion Creative Agent requires the project Remotion skills under .agents/skills")
    return documents


def _remotion_prompt(creative_intent: object, scene_duration: int) -> str:
    """Provide the LLM with director intent, registered capabilities, and local skill guidance."""
    documents = {Path(path).parent.name: Path(path).read_text(encoding="utf-8") for path in load_skill_documents()}
    return json.dumps({
        "role": "Remotion Creative Agent",
        "task": "Turn the Director-owned creative_intent into one executable animation plan for this scene.",
        "creative_intent": creative_intent.model_dump(mode="json"),
        "scene_duration_frames": scene_duration,
        "available_effects": [effect.value for effect in _EFFECT_COMPONENTS],
        "remotion_skill_guidelines": documents,
        "output_contract": {
            "type": "one available_effects value",
            "duration_frames": f"positive integer, at most {scene_duration}",
            "params": "object consumed by the selected EffectRegistry component",
        },
        "rules": [
            "Return exactly one JSON object and no explanation.",
            "Choose an available effect; do not return none or a fade fallback.",
            "Use frame-driven useCurrentFrame, interpolate, spring, transform, opacity, filter, or mask semantics when choosing params.",
            "Do not return asset_id, component names, code, TSX, CSS, crop, cover, scaleX, or scaleY.",
        ],
    }, ensure_ascii=False)


def _transition_prompt(transition_intent: object, from_item, to_item) -> str:
    """Use the same Remotion Creative Agent and skill context for scene boundaries."""
    documents = {Path(path).parent.name: Path(path).read_text(encoding="utf-8") for path in load_skill_documents()}
    return json.dumps({
        "role": "Remotion Creative Agent",
        "task": "Turn the Director-owned transition_intent into one executable scene-boundary transition effect.",
        "transition_intent": transition_intent.model_dump(mode="json"),
        "from_scene": {"asset_id": from_item.asset_id, "duration_frames": from_item.duration_frames},
        "to_scene": {"asset_id": to_item.asset_id, "duration_frames": to_item.duration_frames},
        "transition_effect_capabilities": {effect.value: capability for effect, capability in _TRANSITION_EFFECT_CAPABILITIES.items()},
        "remotion_skill_guidelines": documents,
        "output_contract": {
            "type": "one transition_effect_capabilities key",
            "duration_frames": f"positive integer, at most {min(from_item.duration_frames, to_item.duration_frames)}",
            "params": "object containing only parameters supported by the selected capability",
        },
        "rules": [
            "Return exactly one JSON object and no explanation.",
            "Choose a registered transition effect and use its documented parameters.",
            "Do not return a legacy TransitionConfig type, TSX, React, CSS, or component names.",
            "The transition presentation uses frame-driven transforms, opacity, filters, masks, and fragment layering.",
        ],
    }, ensure_ascii=False)


def _fallback_animation(item) -> AnimationEffect:
    """Local-only fallback for an unavailable Remotion LLM."""
    creative_intent = item.creative_intent
    assert creative_intent is not None
    description = " ".join(filter(None, [creative_intent.description, creative_intent.movement, creative_intent.camera, *creative_intent.effects]))
    normalized = description.lower()
    particle = any(token in normalized for token in ("particle", "particles", "粒子"))
    rotation = any(token in normalized for token in ("flip", "rotate", "rotation", "翻转", "旋转"))
    if particle and rotation:
        effect, duration_frames, params = AnimationEffectType.particle_flip_reveal, min(24, item.duration_frames), {"particle_density": 120, "rotation_axis": "Y", "motion_blur": "blur" in normalized or particle, "perspective": 800, "energy": creative_intent.energy}
    else:
        effect, duration_frames, params = AnimationEffectType.creative_reveal, min(18, item.duration_frames), {"energy": creative_intent.energy, "direction": "up" if any(token in normalized for token in ("up", "bottom", "上", "下")) else "center", "blurPx": 10, "mask": True}
    return AnimationEffect(asset_id=item.asset_id, type=effect, component=_EFFECT_COMPONENTS[effect], implementation="fallback", duration_frames=duration_frames, params=params, design={"creative_intent": creative_intent.model_dump()})


def extract_json_object(raw: str) -> dict:
    """Extract the first JSON object from plain, fenced, or explanatory LLM output."""
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", raw):
        try:
            payload, _ = decoder.raw_decode(raw, match.start())
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise InvalidAnimationResponse("Remotion Agent returned invalid AnimationPlan JSON")


def _safe_raw_response_log(raw: str, limit: int = 1000) -> str:
    return _SECRET.sub("[REDACTED]", raw)[:limit]


def _invalid_response_fallback(item) -> AnimationEffect:
    creative_intent = item.creative_intent
    assert creative_intent is not None
    return AnimationEffect(
        asset_id=item.asset_id,
        type=AnimationEffectType.creative_reveal,
        component=_EFFECT_COMPONENTS[AnimationEffectType.creative_reveal],
        implementation="fallback",
        duration_frames=min(18, item.duration_frames),
        params={},
        design={"creative_intent": creative_intent.model_dump()},
    )


def _parse_llm_animation(raw: str, item) -> AnimationEffect:
    payload = extract_json_object(raw)
    if not isinstance(payload, dict) or set(payload) != {"type", "duration_frames", "params"}:
        raise ValueError("Remotion Agent must return exactly type, duration_frames, and params")
    try:
        effect = AnimationEffectType(payload["type"])
    except (KeyError, ValueError) as exc:
        raise ValueError("Remotion Agent selected an unavailable effect") from exc
    if effect == AnimationEffectType.none or effect not in _EFFECT_COMPONENTS:
        raise ValueError("Remotion Agent cannot select none or an unregistered effect")
    duration_frames = payload.get("duration_frames")
    if not isinstance(duration_frames, int) or isinstance(duration_frames, bool) or not 0 < duration_frames <= item.duration_frames:
        raise ValueError("Remotion Agent returned invalid duration_frames")
    params = payload.get("params")
    if not isinstance(params, dict):
        raise ValueError("Remotion Agent returned invalid params")
    return AnimationEffect(asset_id=item.asset_id, type=effect, component=_EFFECT_COMPONENTS[effect], implementation="new", duration_frames=duration_frames, params=params, design={"creative_intent": item.creative_intent.model_dump()})


def _fallback_transition_effect(from_item, to_item, implementation: str = "fallback") -> TransitionEffectPlanItem:
    intent = from_item.transition_intent
    assert intent is not None
    return TransitionEffectPlanItem(
        from_asset_id=from_item.asset_id,
        to_asset_id=to_item.asset_id,
        type=TransitionEffectType.glass_shatter_transition,
        duration_frames=min(18, from_item.duration_frames, to_item.duration_frames),
        params={"fragment_count": 48, "impact_origin": "center", "motion_blur": True},
        implementation=implementation,
        design={"transition_intent": intent.model_dump()},
    )


def _parse_llm_transition_effect(raw: str, from_item, to_item) -> TransitionEffectPlanItem:
    payload = extract_json_object(raw)
    if not isinstance(payload, dict) or set(payload) != {"type", "duration_frames", "params"}:
        raise ValueError("Remotion Agent must return exactly type, duration_frames, and params")
    try:
        effect = TransitionEffectType(payload["type"])
    except (KeyError, ValueError) as exc:
        # A valid but unknown creative selection is an integration error, never a silent fallback.
        raise ValueError("Remotion Agent selected an unavailable transition effect") from exc
    duration_frames = payload.get("duration_frames")
    if not isinstance(duration_frames, int) or isinstance(duration_frames, bool) or not 0 < duration_frames <= min(from_item.duration_frames, to_item.duration_frames):
        raise ValueError("Remotion Agent returned invalid transition duration_frames")
    params = payload.get("params")
    if not isinstance(params, dict):
        raise ValueError("Remotion Agent returned invalid transition params")
    allowed = set(_TRANSITION_EFFECT_CAPABILITIES[effect]["params"])
    clean_params = {name: value for name, value in params.items() if name in allowed}
    for name in set(params) - allowed:
        logger.warning("[Remotion Agent] Unknown transition parameter ignored: %s", name)
    return TransitionEffectPlanItem(
        from_asset_id=from_item.asset_id,
        to_asset_id=to_item.asset_id,
        type=effect,
        duration_frames=duration_frames,
        params=clean_params,
        implementation="new",
        design={"transition_intent": from_item.transition_intent.model_dump()},
    )


def create_animation_plan(plan: DirectorPlan, mode: str | None = None, provider=None) -> AnimationPlan:
    """Ask the Remotion LLM to convert every CreativeIntent into executable animation."""
    provider = provider or get_agent_provider("remotion")
    animations: list[AnimationEffect] = []
    for item in plan.timeline:
        if item.creative_intent is None:
            continue
        if provider.model_name == "mock":
            logger.warning("[Remotion Agent] LLM unavailable, using fallback")
            animations.append(_fallback_animation(item))
            continue
        logger.info("[Remotion Agent] creative intent analyzed")
        try:
            complete_json = getattr(provider, "complete_json", None) or provider.complete
            raw = complete_json(_remotion_prompt(item.creative_intent, item.duration_frames))
            logger.debug("[Remotion Agent RAW RESPONSE] %s", _safe_raw_response_log(raw))
            animations.append(_parse_llm_animation(raw, item))
        except (OSError, TimeoutError, ConnectionError):
            logger.warning("[Remotion Agent] LLM unavailable, using fallback")
            animations.append(_fallback_animation(item))
        except InvalidAnimationResponse:
            logger.warning("[Remotion Agent] Invalid response, using safe fallback")
            animations.append(_invalid_response_fallback(item))
        else:
            logger.info("[Remotion Agent] generated AnimationPlan")
    return AnimationPlan(animations=animations)


def create_transition_effect_plan(plan: DirectorPlan, provider=None) -> TransitionEffectPlan:
    """Use the existing Remotion Creative Agent to design all requested boundaries."""
    provider = provider or get_agent_provider("remotion")
    transitions: list[TransitionEffectPlanItem] = []
    for index, item in enumerate(plan.timeline[:-1]):
        if item.transition_intent is None:
            continue
        next_item = plan.timeline[index + 1]
        if provider.model_name == "mock":
            logger.warning("[Remotion Agent] LLM unavailable, using fallback")
            transitions.append(_fallback_transition_effect(item, next_item))
            continue
        logger.info("[Remotion Agent] transition intent analyzed")
        try:
            complete_json = getattr(provider, "complete_json", None) or provider.complete
            raw = complete_json(_transition_prompt(item.transition_intent, item, next_item))
            logger.debug("[Remotion Agent RAW RESPONSE] %s", _safe_raw_response_log(raw))
            transitions.append(_parse_llm_transition_effect(raw, item, next_item))
        except (OSError, TimeoutError, ConnectionError):
            logger.warning("[Remotion Agent] LLM unavailable, using fallback")
            transitions.append(_fallback_transition_effect(item, next_item))
        except InvalidAnimationResponse:
            logger.warning("[Remotion Agent] Invalid response, using safe fallback")
            transitions.append(_fallback_transition_effect(item, next_item))
        else:
            logger.info("[Remotion Agent] generated TransitionEffectPlan")
    return TransitionEffectPlan(transitions=transitions)


def create_remotion_plans(plan: DirectorPlan) -> tuple[AnimationPlan, TransitionEffectPlan]:
    """Single visual reasoning entry point for scene animation and transitions."""
    provider = get_agent_provider("remotion")
    return create_animation_plan(plan, provider=provider), create_transition_effect_plan(plan, provider=provider)


def build_advice(state: dict) -> RemotionAdvice:
    storyboard = state["storyboard"]
    if any(scene.motion.type != "static" for scene in storyboard.scenes):
        raise ValueError("Remotion Agent requires static motion unless explicitly approved by a future policy")
    return RemotionAdvice(skill_documents=load_skill_documents())


def remotion_node(state: dict) -> dict:
    advice = build_advice(state)
    plan = state.get("director_plan")
    animation_plan, transition_effect_plan = create_remotion_plans(plan) if plan else (AnimationPlan(), TransitionEffectPlan())
    return {"remotion_advice": advice, "animation_plan": animation_plan, "transition_effect_plan": transition_effect_plan}
