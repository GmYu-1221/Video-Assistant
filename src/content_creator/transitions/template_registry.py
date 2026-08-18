"""Data-only registry for user-provided creative transition templates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TransitionTemplateDefinition:
    id: str
    description: str
    examples: tuple[str, ...] = ()
    avoid_when: tuple[str, ...] = ()
    params: dict[str, dict[str, Any]] = field(default_factory=dict)
    duration_min: int = 1
    duration_max: int = 120
    duration_default: int = 30
    enabled: bool = True


TRANSITION_TEMPLATE_REGISTRY: dict[str, TransitionTemplateDefinition] = {
    "qwen3_8": TransitionTemplateDefinition(
        id="qwen3_8",
        description=(
            "下一张图片以明显模糊状态进入，并从略低的位置轻柔上浮到位；"
            "模糊在入场前段快速消退，位移稍后结束，整体平滑、克制、无抖动、无回弹。"
        ),
        examples=(
            "柔和高级转场",
            "模糊上浮进入",
            "高级感图片切换",
            "平滑轻柔切换",
            "blur then settle",
            "soft float transition",
            "premium smooth transition",
            "elegant image transition",
        ),
        avoid_when=(
            "玻璃破碎",
            "剧烈震动",
            "强冲击切换",
            "水波纹",
            "穿越镜头",
            "明显翻转",
        ),
        params={
            "blur_strength": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "default": 0.8,
                "description": "下一张图片开始进入时的模糊强度。",
            },
            "float_distance": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "default": 0.55,
                "description": "下一张图片从下方向上浮入的距离。",
            },
            "recovery_speed": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "default": 0.7,
                "description": "模糊和位移恢复到静止状态的速度。",
            },
            "opacity_start": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "default": 0.88,
                "description": "下一张图片在转场开始时的不透明度。",
            },
        },
        duration_min=12,
        duration_max=45,
        duration_default=27,
        enabled=True,
    ),
}


def get_transition_template(template_id: str) -> TransitionTemplateDefinition:
    definition = TRANSITION_TEMPLATE_REGISTRY.get(template_id)
    if definition is None:
        raise ValueError(f"Unknown transition template: {template_id}")
    if not definition.enabled:
        raise ValueError(f"Transition template is disabled: {template_id}")
    return definition


def enabled_transition_templates() -> tuple[TransitionTemplateDefinition, ...]:
    return tuple(item for item in TRANSITION_TEMPLATE_REGISTRY.values() if item.enabled)


def get_transition_template_capabilities() -> dict[str, dict[str, Any]]:
    return {
        item.id: {
            "id": item.id,
            "description": item.description,
            "examples": list(item.examples),
            "avoid_when": list(item.avoid_when),
            "params": item.params,
            "duration_frames": {
                "minimum": item.duration_min,
                "maximum": item.duration_max,
                "default": item.duration_default,
            },
        }
        for item in enabled_transition_templates()
    }


def validate_transition_template_params(template_id: str, params: dict[str, Any], duration_frames: int) -> dict[str, Any]:
    definition = get_transition_template(template_id)
    if not definition.duration_min <= duration_frames <= definition.duration_max:
        raise ValueError(
            f"Invalid duration for transition template {template_id}: "
            f"expected {definition.duration_min}-{definition.duration_max}"
        )
    if not isinstance(params, dict):
        raise ValueError(f"Transition template params must be an object: {template_id}")
    clean: dict[str, Any] = {}
    for name, value in params.items():
        specification = definition.params.get(name)
        if specification is None:
            raise ValueError(f"Unknown parameter for transition template {template_id}: {name}")
        kind = specification.get("type")
        if kind == "boolean":
            valid = isinstance(value, bool)
        elif kind == "number":
            valid = isinstance(value, (int, float)) and not isinstance(value, bool)
            valid = valid and specification.get("minimum", float("-inf")) <= value <= specification.get("maximum", float("inf"))
        elif kind == "enum":
            valid = value in specification.get("values", [])
        elif kind == "string":
            valid = isinstance(value, str)
        else:
            valid = False
        if not valid:
            raise ValueError(f"Invalid parameter for transition template {template_id}: {name}")
        clean[name] = value
    return clean
