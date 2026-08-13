"""Remotion Creative Agent: validated director intents -> supported effect plans."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Callable

from content_creator.schemas import (
    AnimationEffect,
    AnimationEffectType,
    AnimationPlan,
    DirectorPlan,
    DirectorTimelineItem,
    RemotionAdvice,
    TransitionEffectPlan,
    TransitionEffectPlanItem,
    TransitionEffectType,
    RemotionCreativePlan,
    RemotionCreativePlanItem,
    VisualEvent,
)
from content_creator.services.llm.router import get_agent_provider

# Runtime knowledge only. Development-only Skills under ~/.codex/skills are not
# prompt material for the provider.
_SKILL_NAMES = (
    "video-assistant-visual-events",
    "remotion-motion-design",
    "stretch-motion-design",
    "remotion-best-practices",
    "remotion-docs",
    "remotion-markup",
    "remotion-render",
)
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
_ANIMATION_EFFECT_CAPABILITIES = {
    AnimationEffectType.card_flip_reveal: {
        "description": "Image flips into view with a card-like 3D rotation.",
        "params": {"rotation_axis": {"type": "enum", "values": ["X", "Y"]}},
    },
    AnimationEffectType.camera_push: {
        "description": "Image receives a subtle cinematic camera push.",
        "params": {"intensity": {"type": "number", "minimum": 0, "maximum": 1}},
    },
    AnimationEffectType.glitch_reveal: {
        "description": "Image resolves through controlled digital glitch layers.",
        "params": {"intensity": {"type": "number", "minimum": 0, "maximum": 1}},
    },
    AnimationEffectType.light_leak: {
        "description": "Image is revealed through a cinematic light-leak wash.",
        "params": {"intensity": {"type": "number", "minimum": 0, "maximum": 1}},
    },
    AnimationEffectType.stretch_reveal: {
        "description": "Image stretches briefly as it resolves into the frame.",
        "params": {"intensity": {"type": "number", "minimum": 0, "maximum": 1}},
    },
    AnimationEffectType.drop_reveal_elastic: {
        "description": "Image drops into the frame from a direction and settles with elastic spring motion.",
        "params": {
            "direction": {"type": "enum", "values": ["top", "bottom", "left", "right"], "description": "Direction the image enters from."},
        },
    },
    AnimationEffectType.particle_flip_reveal: {
        "description": "Image rotates into view with a particle veil.",
        "params": {
            "particle_density": {"type": "number", "minimum": 24, "maximum": 500},
            "rotation_axis": {"type": "enum", "values": ["X", "Y"]},
            "motion_blur": {"type": "boolean"},
            "perspective": {"type": "number", "minimum": 100, "maximum": 2000},
        },
    },
    AnimationEffectType.creative_reveal: {
        "description": "Safe masked reveal with opacity and optional vertical motion.",
        "params": {
            "direction": {"type": "enum", "values": ["up", "center"]},
            "energy": {"type": "number", "minimum": 0, "maximum": 1},
            "blurPx": {"type": "number", "minimum": 0, "maximum": 40},
            "mask": {"type": "boolean"},
        },
    },
}
_TRANSITION_EFFECT_CAPABILITIES = {
    TransitionEffectType.card_flip_transition: {
        "description": "The outgoing image flips in 3D into the next image.",
        "params": {"rotation_axis": {"type": "enum", "values": ["X", "Y"]}, "perspective": {"type": "number", "minimum": 300, "maximum": 2000}},
    },
    TransitionEffectType.glass_shatter_transition: {
        "description": "The outgoing image fractures into cinematic glass-like fragments while the incoming image is revealed behind it.",
        "params": {
            "fragment_count": {"type": "number", "minimum": 12, "maximum": 96, "description": "Number of visible fragment cells."},
            "impact_origin": {"type": "enum", "values": ["center", "left", "right", "top", "bottom"], "description": "Where the glass fracture begins."},
            "motion_blur": {"type": "boolean", "description": "Enable a motion-blur approximation while shards move."},
        },
    },
    TransitionEffectType.shake_transition: {
        "description": "The outgoing image shakes with a short cinematic impact before the next scene resolves into view.",
        "params": {
            "intensity": {"type": "number", "minimum": 0, "maximum": 1, "description": "Strength of the shake."},
            "motion_blur": {"type": "boolean", "description": "Enable blur during the shake."},
        },
    },
}
_VISUAL_EFFECT_CAPABILITIES = {
    **{effect.value: {**capability, "phase": ["entrance", "effect"]} for effect, capability in _ANIMATION_EFFECT_CAPABILITIES.items() if effect.value != "none"},
    **{effect.value: {**capability, "phase": ["transition"]} for effect, capability in _TRANSITION_EFFECT_CAPABILITIES.items()},
}
_TRANSITION_DURATION_RANGES = {
    "card_flip_transition": (18, 60, 30),
    "glass_shatter_transition": (30, 90, 45),
    "shake_transition": (12, 45, 18),
    "particle_dissolve_transition": (24, 90, 36),
    "liquid_morph_transition": (36, 120, 48),
}
logger = logging.getLogger(__name__)
ProgressCallback = Callable[[str], None]
_SECRET = re.compile(r"(?i)(?:authorization\s*:\s*(?:bearer\s+)?|bearer\s+|api[_-]?key\s*[:=]\s*|token\s*[:=]\s*|password\s*[:=]\s*)[^\s,;]+")


class InvalidAnimationResponse(ValueError):
    """Raised only when no JSON object can be recovered from an LLM response."""


class UnknownAnimationEffect(ValueError):
    """A valid response selected an effect that the renderer does not register."""


class UnknownTransitionEffect(ValueError):
    """A valid response selected a transition that the renderer does not register."""


class UnknownVisualEffect(ValueError):
    """A valid unified plan selected an effect absent from the visual registry."""

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
        "animation_effect_capabilities": {effect.value: capability for effect, capability in _ANIMATION_EFFECT_CAPABILITIES.items()},
        "remotion_skill_guidelines": documents,
        "output_contract": {
            "type": "one animation_effect_capabilities key",
            "duration_frames": f"positive integer, at most {scene_duration}",
            "params": "object consumed by the selected EffectRegistry component",
        },
        "rules": [
            "Return only one JSON object with exactly type, duration_frames, and params. Do not return description, explanation, or Markdown.",
            "Choose an available effect; do not return none or a fade fallback.",
            "Choose params only from the selected effect capability.",
            "Example: creative_intent '从上面掉下来入场' returns {\"type\":\"drop_reveal_elastic\",\"duration_frames\":24,\"params\":{\"direction\":\"top\"}}.",
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
            "Return only one JSON object with exactly type, duration_frames, and params. Do not return description, transition_description, implementation_plan, explanation, or Markdown.",
            "Choose a registered transition effect and use its documented parameters.",
            "Choose params only from the selected transition capability.",
            "Example: transition_intent '第二张图片抖动切出' returns {\"type\":\"shake_transition\",\"duration_frames\":18,\"params\":{\"intensity\":0.7,\"motion_blur\":true}}.",
            "Do not return a legacy TransitionConfig type, TSX, React, CSS, or component names.",
            "The transition presentation uses frame-driven transforms, opacity, filters, masks, and fragment layering.",
        ],
    }, ensure_ascii=False)


def _fallback_animation(item) -> AnimationEffect:
    """A safe generic reveal used only when the Remotion LLM is unavailable."""
    creative_intent = item.creative_intent
    assert creative_intent is not None
    effect = AnimationEffectType.creative_reveal
    return AnimationEffect(
        asset_id=item.asset_id,
        type=effect,
        component=_EFFECT_COMPONENTS[effect],
        implementation="fallback",
        duration_frames=min(18, item.duration_frames),
        params={},
        design={"creative_intent": creative_intent.model_dump()},
    )


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


def _plan_fields(raw: str, plan_name: str) -> tuple[object, object, object]:
    """Extract the common plan contract while tolerating non-executable metadata."""
    payload = extract_json_object(raw)
    if not isinstance(payload, dict):
        raise ValueError(f"Remotion Agent returned invalid {plan_name} JSON object")
    missing = {"type", "duration_frames", "params"} - set(payload)
    if missing:
        raise ValueError(f"Remotion Agent {plan_name} is missing required field: {sorted(missing)[0]}")
    return payload["type"], payload["duration_frames"], payload["params"]


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
    effect_value, duration_frames, params = _plan_fields(raw, "AnimationPlan")
    try:
        effect = AnimationEffectType(effect_value)
    except (KeyError, ValueError) as exc:
        raise UnknownAnimationEffect("Remotion Agent selected an unavailable effect") from exc
    if effect == AnimationEffectType.none or effect not in _EFFECT_COMPONENTS:
        raise UnknownAnimationEffect("Remotion Agent cannot select none or an unregistered effect")
    if not isinstance(duration_frames, int) or isinstance(duration_frames, bool) or not 0 < duration_frames <= item.duration_frames:
        raise ValueError("Remotion Agent returned invalid duration_frames")
    if not isinstance(params, dict):
        raise ValueError("Remotion Agent returned invalid params")
    clean_params = _validate_animation_params(effect, params)
    return AnimationEffect(asset_id=item.asset_id, type=effect, component=_EFFECT_COMPONENTS[effect], implementation="new", duration_frames=duration_frames, params=clean_params, design={"creative_intent": item.creative_intent.model_dump()})


def _validate_animation_params(effect: AnimationEffectType, params: dict) -> dict:
    capability = _ANIMATION_EFFECT_CAPABILITIES[effect]
    allowed = capability["params"]
    clean: dict = {}
    for name, value in params.items():
        specification = allowed.get(name)
        if specification is None:
            logger.warning("[Remotion Agent] Unknown animation parameter ignored: %s", name)
            continue
        kind = specification["type"]
        if kind == "boolean":
            valid = isinstance(value, bool)
        elif kind == "number":
            valid = isinstance(value, (int, float)) and not isinstance(value, bool)
            valid = valid and specification.get("minimum", float("-inf")) <= value <= specification.get("maximum", float("inf"))
        elif kind == "enum":
            valid = value in specification["values"]
        else:
            valid = False
        if not valid:
            raise ValueError(f"Remotion Agent returned invalid {effect.value} parameter: {name}")
        clean[name] = value
    return clean


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
    effect_value, duration_frames, params = _plan_fields(raw, "TransitionEffectPlan")
    try:
        effect = TransitionEffectType(effect_value)
    except (KeyError, ValueError) as exc:
        # A valid but unknown creative selection is an integration error, never a silent fallback.
        raise UnknownTransitionEffect("Remotion Agent selected an unavailable transition effect") from exc
    if not isinstance(duration_frames, int) or isinstance(duration_frames, bool) or not 0 < duration_frames <= min(from_item.duration_frames, to_item.duration_frames):
        raise ValueError("Remotion Agent returned invalid transition duration_frames")
    if not isinstance(params, dict):
        raise ValueError("Remotion Agent returned invalid transition params")
    clean_params = _validate_transition_params(effect, params)
    return TransitionEffectPlanItem(
        from_asset_id=from_item.asset_id,
        to_asset_id=to_item.asset_id,
        type=effect,
        duration_frames=duration_frames,
        params=clean_params,
        implementation="new",
        design={"transition_intent": from_item.transition_intent.model_dump()},
    )


def _validate_transition_params(effect: TransitionEffectType, params: dict) -> dict:
    allowed = _TRANSITION_EFFECT_CAPABILITIES[effect]["params"]
    clean: dict = {}
    for name, value in params.items():
        specification = allowed.get(name)
        if specification is None:
            logger.warning("[Remotion Agent] Unknown transition parameter ignored: %s", name)
            continue
        kind = specification["type"]
        if kind == "boolean":
            valid = isinstance(value, bool)
        elif kind == "number":
            valid = isinstance(value, (int, float)) and not isinstance(value, bool)
            valid = valid and specification.get("minimum", float("-inf")) <= value <= specification.get("maximum", float("inf"))
        elif kind == "enum":
            valid = value in specification["values"]
        else:
            valid = False
        if not valid:
            raise ValueError(f"Remotion Agent returned invalid {effect.value} parameter: {name}")
        clean[name] = value
    return clean


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
        except UnknownAnimationEffect:
            raise
        except ValueError:
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
            logger.debug("[Remotion Transition RAW RESPONSE] %s", _safe_raw_response_log(raw))
            transitions.append(_parse_llm_transition_effect(raw, item, next_item))
        except (OSError, TimeoutError, ConnectionError):
            logger.warning("[Remotion Agent] LLM unavailable, using fallback")
            transitions.append(_fallback_transition_effect(item, next_item))
        except InvalidAnimationResponse:
            logger.warning("[Remotion Agent] Invalid response, using safe fallback")
            transitions.append(_fallback_transition_effect(item, next_item))
        except UnknownTransitionEffect:
            raise
        except ValueError:
            logger.warning("[Remotion Agent] Invalid response, using safe fallback")
            transitions.append(_fallback_transition_effect(item, next_item))
        else:
            logger.info("[Remotion Agent] generated TransitionEffectPlan")
    return TransitionEffectPlan(transitions=transitions)


def create_remotion_plans(plan: DirectorPlan) -> tuple[AnimationPlan, TransitionEffectPlan]:
    """Single visual reasoning entry point for scene animation and transitions."""
    provider = get_agent_provider("remotion")
    return create_animation_plan(plan, provider=provider), create_transition_effect_plan(plan, provider=provider)


def _creative_plan_prompt(plan: DirectorPlan) -> str:
    """Batch prompt for the sole visual reasoning call."""
    documents = {Path(path).parent.name: Path(path).read_text(encoding="utf-8") for path in load_skill_documents()}
    scenes = []
    for index, item in enumerate(plan.timeline):
        scenes.append({
            "scene_id": item.asset_id,
            "duration_frames": item.duration_frames,
            "creative_intent": item.creative_intent.model_dump(mode="json") if item.creative_intent else None,
            "transition_intent": item.transition_intent.model_dump(mode="json") if item.transition_intent else None,
            "next_asset_id": plan.timeline[index + 1].asset_id if index + 1 < len(plan.timeline) else None,
        })
    return json.dumps({
        "role": "Remotion Creative Agent",
        "task": "Convert all Director visual intents into one executable unified visual event plan.",
        "scenes": scenes,
        "visual_effect_capabilities": _VISUAL_EFFECT_CAPABILITIES,
        "project_visual_event_rules": documents["video-assistant-visual-events"],
        "remotion_motion_guidelines": documents["remotion-motion-design"],
        "remotion_reference_guidelines": {
            name: content for name, content in documents.items()
            if name not in {"video-assistant-visual-events", "remotion-motion-design"}
        },
        "output_contract": {"plans": [{"scene_id": "asset id", "visual_events": [{"type": "registered effect", "phase": "entrance|exit|transition|camera|effect", "start_frame": "scene-local integer", "duration_frames": "positive integer", "source_asset_id": "required for transition", "target_asset_id": "required for transition", "params": "object"}]}]},
        "rules": [
            "Return only one JSON object with plans; no Markdown or explanation.",
            "Use only registered visual effect types and documented params.",
            "All frame positions are local to the owning scene.",
            "One scene may contain multiple visual_events when their responsibilities are compatible.",
            "A transition event belongs to the source scene and must set target_asset_id.",
            "A transition event owns the reveal of its target asset. Never create entrance, reveal, fade in, creative_reveal, particle_flip_reveal, or drop_reveal for a target asset covered by a transition.",
            "Transitions are cross-scene visual events; entrance animations are single-scene events. If both are requested, keep the transition and remove the target entrance.",
            "Example: '图一玻璃破碎，图二从碎片后出现' returns only a glass_shatter_transition event with source_asset_id image-001 and target_asset_id image-002.",
            "camera_push is a compatible sustained effect and may overlap a transition when the Director requests camera movement before or through the cut. Example: '图一缓慢推进，然后翻转到图二' returns camera_push effect at frames 0-60 plus card_flip_transition at frames 30-60; do not replace this valid combination with a fallback.",
            "card_flip_reveal is entrance-only for one image appearing. card_flip_transition is transition-only for two images changing; use card_flip_transition for '图一图二翻转转场'.",
            "Do not return component names, TSX, React, CSS, or legacy animation/transition fields.",
        ],
    }, ensure_ascii=False)


def _fallback_creative_plan(plan: DirectorPlan) -> RemotionCreativePlan:
    items: list[RemotionCreativePlanItem] = []
    for index, scene in enumerate(plan.timeline):
        events: list[VisualEvent] = []
        if scene.creative_intent:
            events.append(VisualEvent(type="creative_reveal", phase="entrance", start_frame=0, duration_frames=min(18, scene.duration_frames), params={}))
        if scene.transition_intent and index + 1 < len(plan.timeline):
            fallback_duration = min(30, scene.duration_frames, plan.timeline[index + 1].duration_frames)
            events.append(VisualEvent(type="glass_shatter_transition", phase="transition", start_frame=max(0, scene.duration_frames - fallback_duration), duration_frames=fallback_duration, source_asset_id=scene.asset_id, target_asset_id=plan.timeline[index + 1].asset_id, params={"fragment_count": 48, "impact_origin": "center", "motion_blur": True}))
        items.append(RemotionCreativePlanItem(scene_id=scene.asset_id, visual_events=events))
    transition_targets = {event.target_asset_id for item in items for event in item.visual_events if event.phase == "transition"}
    return RemotionCreativePlan(plans=[item.model_copy(update={"visual_events": [event for event in item.visual_events if not (event.phase == "entrance" and item.scene_id in transition_targets)]}) for item in items])


def _validate_visual_event(event: VisualEvent, scene: DirectorTimelineItem, next_asset_id: str | None) -> VisualEvent:
    if event.type not in _VISUAL_EFFECT_CAPABILITIES:
        raise UnknownVisualEffect(f"Remotion Agent selected an unavailable visual effect: {event.type}")
    if event.start_frame + event.duration_frames > scene.duration_frames:
        raise ValueError(f"Visual event exceeds scene duration: {event.type}")
    if event.phase == "transition":
        expected_min, expected_max, _recommended = _TRANSITION_DURATION_RANGES.get(event.type, (1, scene.duration_frames, 1))
        if event.duration_frames < expected_min or event.duration_frames > min(expected_max, scene.duration_frames):
            raise ValueError(f"Invalid duration for {event.type}: expected {expected_min}-{min(expected_max, scene.duration_frames)} frames")
    capability = _VISUAL_EFFECT_CAPABILITIES[event.type]
    clean_params = dict(event.params)
    for name, value in list(clean_params.items()):
        spec = capability.get("params", {}).get(name)
        if spec is None:
            logger.warning("[Remotion Agent] Unknown visual parameter ignored: %s", name)
            clean_params.pop(name)
            continue
        kind = spec["type"]
        valid = (isinstance(value, bool) if kind == "boolean" else value in spec["values"] if kind == "enum" else isinstance(value, (int, float)) and not isinstance(value, bool) and spec.get("minimum", float("-inf")) <= value <= spec.get("maximum", float("inf")))
        if not valid:
            raise ValueError(f"Invalid visual parameter {name} for {event.type}")
    event = event.model_copy(update={"params": clean_params})
    if event.phase == "transition":
        event = event.model_copy(update={"source_asset_id": event.source_asset_id or scene.asset_id, "target_asset_id": event.target_asset_id or next_asset_id})
        if event.target_asset_id != next_asset_id:
            raise ValueError(f"Transition target does not match next scene: {event.type}")
    if event.phase == "transition" and not event.target_asset_id:
        raise ValueError(f"Transition visual event requires target_asset_id: {event.type}")
    return event


def create_remotion_creative_plan(plan: DirectorPlan, provider=None, on_progress: ProgressCallback | None = None) -> RemotionCreativePlan:
    """Single LLM entry point for all scene and transition visual decisions."""
    provider = provider or get_agent_provider("remotion")
    if provider.model_name == "mock":
        logger.warning("[Remotion Agent] LLM unavailable, using fallback")
        return _fallback_creative_plan(plan)
    try:
        if on_progress:
            on_progress("Remotion 创意引擎|正在设计视觉效果...")
        complete_json = getattr(provider, "complete_json", None) or provider.complete
        raw = complete_json(_creative_plan_prompt(plan))
        if on_progress:
            on_progress("视觉事件|正在解析并验证视觉计划...")
        logger.debug("[Remotion Agent RAW RESPONSE] %s", _safe_raw_response_log(raw))
        payload = extract_json_object(raw)
        parsed = RemotionCreativePlan.model_validate(payload)
        scene_map = {scene.asset_id: scene for scene in plan.timeline}
        next_map = {plan.timeline[i].asset_id: plan.timeline[i + 1].asset_id for i in range(len(plan.timeline) - 1)}
        validated = []
        for item in parsed.plans:
            scene = scene_map.get(item.scene_id)
            if scene is None:
                raise ValueError(f"Remotion Agent returned unknown scene_id: {item.scene_id}")
            validated.append(item.model_copy(update={"visual_events": [_validate_visual_event(event, scene, next_map.get(item.scene_id)) for event in item.visual_events]}))
        # A transition owns source/target reveal. Camera push is deliberately a
        # compatible sustained effect; competing entrance/reveal events are not.
        incoming = {event.target_asset_id: event for item in validated for event in item.visual_events if event.phase == "transition" and event.target_asset_id}
        outgoing = {item.scene_id: [event for event in item.visual_events if event.phase == "transition"] for item in validated}
        cleaned = []
        for item in validated:
            transitions = outgoing.get(item.scene_id, [])
            kept = []
            for event in item.visual_events:
                if event.phase == "transition":
                    kept.append(event)
                    continue
                if item.scene_id in incoming:
                    continue
                overlaps = any(event.start_frame < transition.start_frame + transition.duration_frames and transition.start_frame < event.start_frame + event.duration_frames for transition in transitions)
                if event.type == "camera_push" or not overlaps:
                    kept.append(event)
            cleaned.append(item.model_copy(update={"visual_events": kept}))
        validated = cleaned
        logger.info("[Remotion Agent] generated RemotionCreativePlan")
        return RemotionCreativePlan(plans=validated)
    except (OSError, TimeoutError, ConnectionError):
        logger.warning("[Remotion Agent] LLM unavailable, using fallback")
    except UnknownVisualEffect:
        raise
    except (InvalidAnimationResponse, ValueError):
        logger.warning("[Remotion Agent] Invalid response, using safe fallback")
    return _fallback_creative_plan(plan)


def build_advice(state: dict) -> RemotionAdvice:
    storyboard = state["storyboard"]
    if any(scene.motion.type != "static" for scene in storyboard.scenes):
        raise ValueError("Remotion Agent requires static motion unless explicitly approved by a future policy")
    return RemotionAdvice(skill_documents=load_skill_documents())


def remotion_node(state: dict) -> dict:
    advice = build_advice(state)
    plan = state.get("director_plan")
    creative_plan = create_remotion_creative_plan(plan) if plan else RemotionCreativePlan()
    return {"remotion_advice": advice, "remotion_creative_plan": creative_plan}
