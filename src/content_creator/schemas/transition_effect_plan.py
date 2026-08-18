"""Creative transition plans produced by the Remotion Creative Agent."""

from __future__ import annotations

import math
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_serializer, model_validator


_FORBIDDEN_TEMPLATE_KEYS = {"component", "tsx", "css", "javascript", "code", "path", "module", "import", "function"}


def _validate_json_safe(value: Any, path: str = "parameters") -> None:
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"Transition template parameter is not JSON-safe: {path}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_safe(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or key.lower() in _FORBIDDEN_TEMPLATE_KEYS:
                raise ValueError(f"Forbidden transition template parameter: {key}")
            _validate_json_safe(item, f"{path}.{key}")
        return
    raise ValueError(f"Transition template parameter is not JSON-safe: {path}")


class TransitionEffectType(str, Enum):
    """Stable infrastructure type; concrete visuals live in the template registry."""

    template_transition = "template_transition"


class TransitionEffectPlanItem(BaseModel):
    from_asset_id: str = Field(min_length=1)
    to_asset_id: str = Field(min_length=1)
    type: TransitionEffectType
    duration_frames: int = Field(gt=0)
    params: dict[str, Any] = Field(default_factory=dict)
    implementation: Literal["new", "fallback"] = "new"
    design: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_template_contract(self):
        if set(self.params) - {"template_id", "parameters"}:
            raise ValueError("template_transition params contain renderer implementation fields")
        template_id = self.params.get("template_id")
        parameters = self.params.get("parameters", {})
        if not isinstance(template_id, str) or not template_id:
            raise ValueError("template_transition requires template_id")
        if not isinstance(parameters, dict):
            raise ValueError("template_transition parameters must be an object")
        _validate_json_safe(parameters)
        if template_id != "qwen3_8":
            raise ValueError(f"Unknown transition template: {template_id}")
        return self

    @model_serializer
    def serialize_for_render(self) -> dict[str, Any]:
        return {
            "from_asset_id": self.from_asset_id,
            "to_asset_id": self.to_asset_id,
            "type": self.type.value,
            "duration_frames": self.duration_frames,
            "params": self.params,
            "implementation": self.implementation,
            "design": self.design,
        }


class TransitionEffectPlan(BaseModel):
    transitions: list[TransitionEffectPlanItem] = Field(default_factory=list)
