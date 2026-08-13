"""Creative transition plans produced by the Remotion Creative Agent."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_serializer


class TransitionEffectType(str, Enum):
    glass_shatter_transition = "glass_shatter_transition"
    shake_transition = "shake_transition"


class TransitionEffectPlanItem(BaseModel):
    from_asset_id: str = Field(min_length=1)
    to_asset_id: str = Field(min_length=1)
    type: TransitionEffectType
    duration_frames: int = Field(gt=0)
    params: dict[str, Any] = Field(default_factory=dict)
    implementation: Literal["new", "fallback"] = "new"
    design: dict[str, Any] = Field(default_factory=dict)

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
