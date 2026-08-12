"""Implementation-neutral animation plan produced by the Remotion Creative Agent."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class AnimationEffectType(str, Enum):
    none = "none"
    card_flip_reveal = "card_flip_reveal"
    camera_push = "camera_push"
    glitch_reveal = "glitch_reveal"
    light_leak = "light_leak"


class AnimationEffect(BaseModel):
    asset_id: str = Field(min_length=1)
    effect: AnimationEffectType = AnimationEffectType.none
    component: str = "FadeFallback"
    implementation: Literal["custom", "fallback"] = "fallback"
    duration_frames: int = Field(default=1, gt=0)
    props: dict[str, Any] = Field(default_factory=dict)
    fallback: AnimationEffectType = AnimationEffectType.none


class AnimationPlan(BaseModel):
    animations: list[AnimationEffect] = Field(default_factory=list)
