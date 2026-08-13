"""Implementation-neutral animation plan produced by the Remotion Creative Agent."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field, model_serializer


class AnimationEffectType(str, Enum):
    none = "none"
    card_flip_reveal = "card_flip_reveal"
    camera_push = "camera_push"
    glitch_reveal = "glitch_reveal"
    light_leak = "light_leak"
    stretch_reveal = "stretch_reveal"
    elastic_blur_reveal = "elastic_blur_reveal"
    drop_reveal_elastic = "drop_reveal_elastic"
    particle_flip_reveal = "particle_flip_reveal"
    creative_reveal = "creative_reveal"


class AnimationEffect(BaseModel):
    asset_id: str = Field(min_length=1)
    type: AnimationEffectType = Field(default=AnimationEffectType.none, validation_alias=AliasChoices("type", "effect"))
    component: str = "CreativeReveal"
    implementation: Literal["custom", "fallback", "new"] = "new"
    duration_frames: int = Field(default=1, gt=0)
    params: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("params", "props"))
    fallback: AnimationEffectType = AnimationEffectType.none
    design: dict[str, Any] = Field(default_factory=dict)

    @property
    def effect(self) -> AnimationEffectType:
        """Backward-compatible alias for pre-type/params Python callers."""
        return self.type

    @property
    def props(self) -> dict[str, Any]:
        """Backward-compatible alias for pre-type/params Python callers."""
        return self.params

    @model_serializer
    def serialize_for_render(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "asset_id": self.asset_id,
            "type": self.type.value,
            "duration_frames": self.duration_frames,
            "params": self.params,
            "component": self.component,
            "implementation": self.implementation,
            "fallback": self.fallback.value,
            "design": self.design,
        }
        return payload


class AnimationPlan(BaseModel):
    animations: list[AnimationEffect] = Field(default_factory=list)
