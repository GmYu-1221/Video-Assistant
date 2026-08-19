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
    VisualSpecDecision,
)
from content_creator.services.llm.router import get_agent_provider
from content_creator.transitions import (
    enabled_transition_templates,
    get_transition_template_capabilities,
    validate_transition_template_params,
)

# Runtime knowledge only. Development-only Skills under ~/.codex/skills are not
# prompt material for the provider.
_SKILL_NAMES = (
    "remotion-motion-design",
    "stretch-motion-design",
    "elastic-blur-motion-design",
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
    AnimationEffectType.elastic_blur_reveal: "ElasticBlurReveal",
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
        "params": {
            "intensity": {"type": "number", "minimum": 0, "maximum": 1},
            "motion_blur": {"type": "boolean"},
        },
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
    AnimationEffectType.elastic_blur_reveal: {
        "description": "Image enters with weighted horizontal stretch, vertical compression, slight blur, and an elastic settle to a fully static image.",
        "params": {
            "intensity": {"type": "number", "minimum": 0, "maximum": 1},
            "blur_px": {"type": "number", "minimum": 0, "maximum": 24},
            "opacity": {"type": "number", "minimum": 0, "maximum": 1},
        },
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
_ANIMATION_EFFECT_PHASES = {
    AnimationEffectType.card_flip_reveal: ["entrance"],
    AnimationEffectType.camera_push: ["camera"],
    AnimationEffectType.glitch_reveal: ["entrance"],
    AnimationEffectType.light_leak: ["effect"],
    AnimationEffectType.stretch_reveal: ["entrance"],
    AnimationEffectType.elastic_blur_reveal: ["entrance"],
    AnimationEffectType.drop_reveal_elastic: ["entrance"],
    AnimationEffectType.particle_flip_reveal: ["entrance"],
    AnimationEffectType.creative_reveal: ["entrance"],
}
_ANIMATION_VISUAL_CAPABILITIES = {
    **{
        effect.value: {**capability, "phase": _ANIMATION_EFFECT_PHASES[effect]}
        for effect, capability in _ANIMATION_EFFECT_CAPABILITIES.items()
        if effect.value != "none"
    },
}


def _visual_effect_capabilities() -> dict[str, dict]:
    capabilities = dict(_ANIMATION_VISUAL_CAPABILITIES)
    templates = get_transition_template_capabilities()
    if templates:
        capabilities[TransitionEffectType.template_transition.value] = {
            "description": "A registered scene-boundary transition template.",
            "templates": templates,
            "params": {
                "template_id": {"type": "enum", "values": list(templates)},
                "parameters": {"type": "object"},
            },
            "phase": ["transition"],
        }
    return capabilities
logger = logging.getLogger(__name__)
ProgressCallback = Callable[[str], None]
_SECRET = re.compile(r"(?i)(?:authorization\s*:\s*(?:bearer\s+)?|bearer\s+|api[_-]?key\s*[:=]\s*|token\s*[:=]\s*|password\s*[:=]\s*)[^\s,;]+")
_CAMERA_PUSH_INTENT = re.compile(r"(?:缓慢推进|镜头推进|push\s*in|zoom\s*in|camera\s+movement|ken\s*burns)", re.IGNORECASE)


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
            "Use elastic_blur_reveal for explicit weighted elastic entrance with light lens blur. It is entrance-only, lasts 18-36 frames, and must settle fully static. Never create elastic_blur_transition or stretch_transition.",
            "Use frame-driven useCurrentFrame, interpolate, spring, transform, opacity, filter, or mask semantics when choosing params.",
            "Do not return asset_id, component names, code, TSX, CSS, crop, cover, scaleX, or scaleY.",
        ],
    }, ensure_ascii=False)


def _transition_prompt(transition_intent: object, from_item, to_item) -> str:
    """Prompt only currently registered transition templates."""
    documents = {Path(path).parent.name: Path(path).read_text(encoding="utf-8") for path in load_skill_documents()}
    return json.dumps({
        "role": "Remotion Creative Agent",
        "task": "Turn the Director-owned transition_intent into one registered template transition, or omit it when no template fits.",
        "transition_intent": transition_intent.model_dump(mode="json"),
        "from_scene": {"asset_id": from_item.asset_id, "duration_frames": from_item.duration_frames},
        "to_scene": {"asset_id": to_item.asset_id, "duration_frames": to_item.duration_frames},
        "transition_template_capabilities": get_transition_template_capabilities(),
        "remotion_skill_guidelines": documents,
        "output_contract": {
            "type": "template_transition",
            "duration_frames": f"positive integer, at most {min(from_item.duration_frames, to_item.duration_frames)}",
            "params": "{template_id: string, parameters: JSON-safe object}",
        },
        "rules": [
            "Return only one JSON object with exactly type, duration_frames, and params, or an empty object when no template is registered. Do not return Markdown.",
            "Use only a template_id present in transition_template_capabilities.",
            "Never invent a template, renderer, component, TSX, CSS, path, module, import, or code.",
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
    if effect == AnimationEffectType.elastic_blur_reveal and not 18 <= duration_frames <= 36:
        raise ValueError("Remotion Agent returned invalid elastic_blur_reveal duration_frames")
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


def _parse_llm_transition_effect(raw: str, from_item, to_item) -> TransitionEffectPlanItem:
    effect_value, duration_frames, params = _plan_fields(raw, "TransitionEffectPlan")
    if effect_value != TransitionEffectType.template_transition.value:
        raise UnknownTransitionEffect("Remotion Agent selected an unavailable transition effect")
    if not isinstance(duration_frames, int) or isinstance(duration_frames, bool) or not 0 < duration_frames <= min(from_item.duration_frames, to_item.duration_frames):
        raise ValueError("Remotion Agent returned invalid transition duration_frames")
    if not isinstance(params, dict):
        raise ValueError("Remotion Agent returned invalid transition params")
    template_id = params.get("template_id")
    if not isinstance(template_id, str) or not template_id:
        raise ValueError("Remotion Agent returned no transition template_id")
    clean_params = {"template_id": template_id, "parameters": validate_transition_template_params(template_id, params.get("parameters", {}), duration_frames)}
    return TransitionEffectPlanItem(
        from_asset_id=from_item.asset_id,
        to_asset_id=to_item.asset_id,
        type=TransitionEffectType.template_transition.value,
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
        except InvalidAnimationResponse as exc:
            logger.warning("[Remotion Agent] Invalid response, using safe fallback (%s)", exc)
            animations.append(_invalid_response_fallback(item))
        except UnknownAnimationEffect:
            raise
        except ValueError as exc:
            logger.warning("[Remotion Agent] Invalid response, using safe fallback (%s)", exc)
            animations.append(_invalid_response_fallback(item))
        else:
            logger.info("[Remotion Agent] generated AnimationPlan")
    return AnimationPlan(animations=animations)


def create_transition_effect_plan(plan: DirectorPlan, provider=None) -> TransitionEffectPlan:
    """Design registered templates only; an empty registry means no effect."""
    if not enabled_transition_templates():
        logger.warning("[Remotion Agent] No registered transition templates; skipping creative transition")
        return TransitionEffectPlan(transitions=[])
    provider = provider or get_agent_provider("remotion")
    transitions: list[TransitionEffectPlanItem] = []

    def qwen_fallback(item, next_item, reason: str) -> TransitionEffectPlanItem | None:
        duration = min(27, item.duration_frames, next_item.duration_frames)
        if duration < 12:
            return None
        return TransitionEffectPlanItem(
            from_asset_id=item.asset_id,
            to_asset_id=next_item.asset_id,
            type=TransitionEffectType.template_transition,
            duration_frames=duration,
            params={"template_id": "qwen3_8", "parameters": {
                "blur_strength": 0.8,
                "float_distance": 0.55,
                "recovery_speed": 0.7,
                "opacity_start": 0.88,
            }},
            design={"requested_template_id": None, "resolved_template_id": "qwen3_8", "fallback_reason": reason},
        )

    for index, item in enumerate(plan.timeline[:-1]):
        if item.transition_intent is None:
            continue
        next_item = plan.timeline[index + 1]
        if provider.model_name == "mock":
            logger.warning("[Remotion Agent] LLM unavailable; using qwen3_8 fallback")
            fallback = qwen_fallback(item, next_item, "model_unavailable")
            if fallback:
                transitions.append(fallback)
            continue
        logger.info("[Remotion Agent] transition intent analyzed")
        try:
            complete_json = getattr(provider, "complete_json", None) or provider.complete
            raw = complete_json(_transition_prompt(item.transition_intent, item, next_item))
            logger.debug("[Remotion Transition RAW RESPONSE] %s", _safe_raw_response_log(raw))
            transitions.append(_parse_llm_transition_effect(raw, item, next_item))
        except (OSError, TimeoutError, ConnectionError) as exc:
            logger.warning("[Remotion Agent] LLM unavailable; using qwen3_8 fallback")
            fallback = qwen_fallback(item, next_item, "model_unavailable")
            if fallback:
                transitions.append(fallback)
        except InvalidAnimationResponse as exc:
            logger.warning("[Remotion Agent] Invalid response; using qwen3_8 fallback (%s)", exc)
            fallback = qwen_fallback(item, next_item, "invalid_response")
            if fallback:
                transitions.append(fallback)
        except UnknownTransitionEffect as exc:
            logger.warning("[Remotion Agent] Unavailable transition; using qwen3_8 fallback (%s)", exc)
            fallback = qwen_fallback(item, next_item, "unknown_template")
            if fallback:
                transitions.append(fallback)
        except ValueError as exc:
            logger.warning("[Remotion Agent] Invalid response; using qwen3_8 fallback (%s)", exc)
            fallback = qwen_fallback(item, next_item, "invalid_response")
            if fallback:
                transitions.append(fallback)
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
        "visual_effect_capabilities": _visual_effect_capabilities(),
        "project_visual_event_rules": "Entrance and camera events are single-scene effects. Scene-boundary creative transitions may only use registered template_transition entries.",
        "remotion_motion_guidelines": documents["remotion-motion-design"],
        "remotion_reference_guidelines": {
            name: content for name, content in documents.items()
            if name != "remotion-motion-design"
        },
        "output_contract": {"plans": [{"scene_id": "asset id", "visual_events": [{"type": "registered effect", "phase": "entrance|exit|transition|camera|effect", "start_frame": "scene-local integer", "duration_frames": "positive integer", "source_asset_id": "required for transition", "target_asset_id": "required for transition", "params": "object"}]}]},
        "rules": [
            "Return only one JSON object with plans; no Markdown or explanation.",
            "Use only registered visual effect types and documented params.",
            "All frame positions are local to the owning scene.",
            "One scene may contain multiple visual_events when their responsibilities are compatible.",
            "Entrance events are short, self-contained arrivals: default to 10-30 frames (18 frames when no timing is specified). Never use the full scene duration unless the Director explicitly requests continuous motion.",
            "After an entrance event ends, the image must hold static: scale 1, rotate 0, translate 0, opacity 1. An entrance effect must not influence the remaining scene frames.",
            "Example: '图片丝滑拉伸进入' returns a stretch_reveal entrance event with duration_frames 18; after frame 18, emit no entrance motion.",
            "Use elastic_blur_reveal only for an image entering with weight, elastic rebound, and light lens blur. It is phase entrance, duration 18-36 frames, and must end at scale 1, rotate 0, translate 0, opacity 1, blur 0. Never output elastic_blur_transition or stretch_transition.",
            "A transition event belongs to the source scene and must set target_asset_id.",
            "A transition event owns the reveal of its target asset. Never create entrance, reveal, fade in, creative_reveal, particle_flip_reveal, or drop_reveal for a target asset covered by a transition.",
            "Transitions are cross-scene visual events; entrance animations are single-scene events. If both are requested, keep the transition and remove the target entrance.",
            "Output template_transition only when visual_effect_capabilities includes it, and choose only a listed template_id.",
            "If no transition template is exposed, do not emit a transition event even when transition_intent is present.",
            "Generate camera_push only when the Director explicitly requests 缓慢推进, 镜头推进, push in, zoom in, camera movement, or Ken Burns. Never infer it from cinematic, dramatic, smooth, premium, entrance, or transition.",
            "card_flip_reveal remains an entrance-only animation and is not a scene-boundary transition.",
            "Do not return component names, TSX, React, CSS, or legacy animation/transition fields.",
        ],
    }, ensure_ascii=False)


def _visual_spec_decision_prompt(plan: DirectorPlan) -> str:
    """仅向模型暴露受控的视觉决策，不暴露渲染器实现。"""
    boundaries = [
        {"from_asset_id": item.asset_id, "to_asset_id": plan.timeline[index + 1].asset_id,
         "transition_intent": item.transition_intent.model_dump(mode="json") if item.transition_intent else None}
        for index, item in enumerate(plan.timeline[:-1])
    ]
    return json.dumps({
        "role": "视觉规格决策 Agent",
        "task": "从已注册能力中选择一个画面布局，并为需要处理的相邻场景边界选择一个转场预设。",
        "可用布局": {"center_stage": "上下区域可固定文字，中间图片舞台切换", "fullscreen": "图片占满整个画面"},
        "available_transition_presets": {
            "clean_cut": "直接切换，无过渡",
            "crossfade": "交叉淡入淡出",
            "white_flash": {"说明": "白色闪光覆盖", "flash_peak": "0 到 1"},
            "flash_zoom_blur": {"说明": "短促白闪后，新图由放大和模糊状态恢复清晰", "flash_peak": "0 到 1", "incoming_scale": "0.5 到 3", "blur_px": "0 到 80", "settle_frames": "正整数"},
        },
        "待决策的相邻场景边界": boundaries,
        "输出格式": {"layout_preset": "已注册的英文布局枚举", "transitions": [{"from_asset_id": "输入中给出的起始素材 ID", "to_asset_id": "输入中给出的目标素材 ID", "preset": "已注册的英文预设枚举", "params": "仅可填写该预设文档列出的数值参数"}]},
        "rules": [
            "只返回一个 JSON 对象，不要输出 Markdown、解释或额外文字。",
            "不得输出 TSX、CSS、React、代码、动画轨道、区域定义、图层定义或未注册名称。",
            "当意图是短促白闪，且新图片从模糊放大状态恢复清晰时，使用 flash_zoom_blur。",
            "只能填写输入给出的相邻场景边界。省略某个边界时，本地渲染器会使用默认效果。",
        ],
    }, ensure_ascii=False)


def create_visual_spec_decision(plan: DirectorPlan, provider=None) -> VisualSpecDecision:
    """Ask for the small LLM-owned decision layer; preserve deterministic fallback."""
    provider = provider or get_agent_provider("remotion")
    fallback = VisualSpecDecision()
    if provider.model_name == "mock":
        return fallback
    try:
        complete_json = getattr(provider, "complete_json", None) or provider.complete
        decision = VisualSpecDecision.model_validate(extract_json_object(complete_json(_visual_spec_decision_prompt(plan))))
        expected = {(item.asset_id, plan.timeline[index + 1].asset_id) for index, item in enumerate(plan.timeline[:-1])}
        if any((entry.from_asset_id, entry.to_asset_id) not in expected for entry in decision.transitions):
            raise ValueError("Visual Spec decision references a non-adjacent scene boundary")
        return decision
    except Exception as exc:
        logger.warning("[Visual Spec Agent] Invalid or unavailable decision, using local defaults (%s)", type(exc).__name__)
        return fallback


def _fallback_creative_plan(plan: DirectorPlan) -> RemotionCreativePlan:
    items: list[RemotionCreativePlanItem] = []
    for index, scene in enumerate(plan.timeline):
        events: list[VisualEvent] = []
        if scene.creative_intent:
            events.append(VisualEvent(type="creative_reveal", phase="entrance", start_frame=0, duration_frames=min(18, scene.duration_frames), params={}))
        items.append(RemotionCreativePlanItem(scene_id=scene.asset_id, visual_events=events))
    transition_targets = {event.target_asset_id for item in items for event in item.visual_events if event.phase == "transition"}
    return RemotionCreativePlan(plans=[item.model_copy(update={"visual_events": [event for event in item.visual_events if not (event.phase == "entrance" and item.scene_id in transition_targets)]}) for item in items])


def _validate_visual_event(event: VisualEvent, scene: DirectorTimelineItem, next_asset_id: str | None) -> VisualEvent:
    capabilities = _visual_effect_capabilities()
    if event.type not in capabilities:
        raise UnknownVisualEffect(f"Remotion Agent selected an unavailable visual effect: {event.type}")
    capability = capabilities[event.type]
    allowed_phases = capability["phase"]
    if event.phase not in allowed_phases:
        raise ValueError(f"Invalid phase for {event.type}: expected {', '.join(allowed_phases)}")
    if event.start_frame + event.duration_frames > scene.duration_frames:
        raise ValueError(f"Visual event exceeds scene duration: {event.type}")
    if event.phase == "transition":
        template_id = event.params.get("template_id")
        if not isinstance(template_id, str):
            raise ValueError("template_transition requires template_id")
        parameters = validate_transition_template_params(template_id, event.params.get("parameters", {}), event.duration_frames)
        event = event.model_copy(update={"params": {"template_id": template_id, "parameters": parameters}})
    if event.type == AnimationEffectType.elastic_blur_reveal.value:
        if event.phase != "entrance":
            raise ValueError("elastic_blur_reveal must use entrance phase")
        if not 18 <= event.duration_frames <= min(36, scene.duration_frames):
            raise ValueError(f"Invalid duration for elastic_blur_reveal: expected 18-{min(36, scene.duration_frames)} frames")
    clean_params = dict(event.params)
    if event.phase == "transition":
        clean_params = event.params
    else:
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


def _explicitly_requests_camera_push(scene: DirectorTimelineItem) -> bool:
    """Require explicit camera-motion language before preserving camera_push."""
    intent = scene.creative_intent
    if intent is None:
        return False
    text = " ".join(filter(None, [intent.description, intent.movement, intent.camera, intent.timing, *intent.effects]))
    return bool(_CAMERA_PUSH_INTENT.search(text))


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
            events = []
            for event in item.visual_events:
                try:
                    events.append(_validate_visual_event(event, scene, next_map.get(item.scene_id)))
                except (UnknownVisualEffect, ValueError) as exc:
                    logger.warning(
                        "[VisualEvent Validation]\nDropped event:\ntype: %s\nreason: %s",
                        event.type,
                        exc,
                    )
            validated.append(item.model_copy(update={"visual_events": events}))
        # A transition owns source/target reveal. Camera push survives only for
        # explicit camera-motion direction.
        incoming = {event.target_asset_id: event for item in validated for event in item.visual_events if event.phase == "transition" and event.target_asset_id}
        outgoing = {item.scene_id: [event for event in item.visual_events if event.phase == "transition"] for item in validated}
        cleaned = []
        for item in validated:
            scene = scene_map[item.scene_id]
            transitions = outgoing.get(item.scene_id, [])
            kept = []
            for event in item.visual_events:
                if event.phase == "transition":
                    kept.append(event)
                    continue
                if item.scene_id in incoming:
                    continue
                overlaps = any(event.start_frame < transition.start_frame + transition.duration_frames and transition.start_frame < event.start_frame + event.duration_frames for transition in transitions)
                if event.type == "camera_push":
                    if _explicitly_requests_camera_push(scene):
                        kept.append(event)
                    continue
                if not overlaps:
                    kept.append(event)
            cleaned.append(item.model_copy(update={"visual_events": kept}))
        validated = cleaned
        kept_event_count = sum(len(item.visual_events) for item in validated)
        logger.info("[VisualEvent Validation]\nKept events:\ncount: %d", kept_event_count)
        if kept_event_count == 0:
            logger.warning("[Remotion Agent] No valid visual events, using safe fallback")
            return _fallback_creative_plan(plan)
        logger.info("[Remotion Agent] generated RemotionCreativePlan")
        return RemotionCreativePlan(plans=validated)
    except UnknownVisualEffect:
        raise
    except Exception as exc:
        # Providers may surface transport failures as SDK-specific exceptions
        # rather than OSError/ConnectionError. Rendering must stay local-first.
        logger.warning("[Remotion Agent] LLM unavailable, using fallback (%s)", type(exc).__name__)
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
