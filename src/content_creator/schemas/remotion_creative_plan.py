"""Unified visual events produced by the Remotion Creative Agent."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class VisualEvent(BaseModel):
    type: str = Field(min_length=1)
    phase: Literal["entrance", "exit", "transition", "camera", "effect"]
    start_frame: int = Field(default=0, ge=0)
    duration_frames: int = Field(gt=0)
    source_asset_id: str | None = None
    target_asset_id: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class RemotionCreativePlanItem(BaseModel):
    scene_id: str = Field(min_length=1)
    visual_events: list[VisualEvent] = Field(default_factory=list)


class RemotionCreativePlan(BaseModel):
    plans: list[RemotionCreativePlanItem] = Field(default_factory=list)
