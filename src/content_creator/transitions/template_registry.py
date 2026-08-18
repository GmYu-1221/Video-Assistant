"""Data-only registry for user-provided creative transition templates.

The production registry is intentionally empty until a template is explicitly
implemented and registered in both Python and Remotion.
"""

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


TRANSITION_TEMPLATE_REGISTRY: dict[str, TransitionTemplateDefinition] = {}


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
