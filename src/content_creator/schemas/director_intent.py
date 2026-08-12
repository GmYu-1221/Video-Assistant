"""Structured, implementation-neutral intents emitted by Director Chat."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AnimationIntent(BaseModel):
    type: str = Field(min_length=1, max_length=80)
    direction: str | None = None
    speed: Literal["slow", "medium", "fast"] = "medium"
    emotion: str | None = None
    camera_motion: str | None = None
    visual_effect: str | None = None
    duration_frames: int = Field(default=18, gt=0, le=120)


class DirectorIntent(BaseModel):
    """A safe delta to apply to a DirectorPlan; never contains code or frame ranges."""

    target_index: int | None = Field(default=None, ge=0)
    animation_intent: AnimationIntent | None = None
    transition_duration_frames: int | None = Field(default=None, gt=0, le=60)
    energy: Literal["low", "medium", "high"] | None = None
    style: str | None = None
    response: str = Field(default="Plan updated.", min_length=1, max_length=500)
