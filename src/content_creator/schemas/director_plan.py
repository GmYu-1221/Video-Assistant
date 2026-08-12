"""Validated, provider-neutral director decisions for an image video."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .transition import TransitionConfig
from .creative_intent import CreativeIntent


class DirectorTimelineItem(BaseModel):
    asset_id: str = Field(min_length=1)
    duration_frames: int = Field(gt=0)
    transition: TransitionConfig = Field(default_factory=TransitionConfig)
    transition_strength: float = Field(default=0.5, ge=0, le=1)
    motion: Literal["static"] = "static"
    reason: str = Field(default="Balanced pacing.", min_length=1, max_length=500)
    creative_intent: CreativeIntent | None = None
    timing: str | None = Field(default=None, max_length=160)


class DirectorPlan(BaseModel):
    """The only JSON contract an LLM may return for director decisions."""

    timeline: list[DirectorTimelineItem] = Field(min_length=1)
