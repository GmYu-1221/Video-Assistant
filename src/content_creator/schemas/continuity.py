"""URL-only continuity decisions and staged resolved timeline state."""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .transition import TransitionConfig


class StateAction(str, Enum):
    hold = "hold"
    replace = "replace"


class CopyAction(str, Enum):
    hold = "hold"
    replace = "replace"
    hide = "hide"


class LayoutAction(str, Enum):
    hold = "hold"
    adapt = "adapt"
    replace = "replace"


class BoundaryAction(str, Enum):
    continuous = "continuous"
    accent = "accent"
    scene_cut = "scene_cut"


class DirectorTimelineAction(BaseModel):
    segment_id: str = Field(min_length=1)
    scene_id: str = Field(min_length=1)
    duration_frames: int = Field(gt=0)
    scene_purpose: str | None = None
    media_action: StateAction
    copy_action: CopyAction
    layout_action: LayoutAction
    boundary_action: BoundaryAction
    replacement_media_id: str | None = None
    narrative_source_ids: list[str] = Field(default_factory=list)
    transition: TransitionConfig = Field(default_factory=TransitionConfig, exclude=True)
    reason: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def replacement_references(self) -> "DirectorTimelineAction":
        if self.media_action == StateAction.replace and not self.replacement_media_id:
            raise ValueError("media replace requires replacement_media_id")
        if self.copy_action == CopyAction.replace and not self.narrative_source_ids:
            raise ValueError("copy replace requires narrative_source_ids")
        return self


class PartialTimelineItem(BaseModel):
    segment_id: str
    scene_id: str
    duration_frames: int
    scene_purpose: str | None = None
    resolved_media_id: str
    copy_action: CopyAction
    layout_action: LayoutAction
    boundary_action: BoundaryAction
    narrative_source_ids: list[str] = Field(default_factory=list)
    transition: TransitionConfig = Field(exclude=True)


class ResolvedTimelineItem(BaseModel):
    segment_id: str
    scene_id: str
    start_frame: int = Field(ge=0)
    end_frame: int = Field(gt=0)
    duration_frames: int = Field(gt=0)
    resolved_media_id: str
    resolved_copy_id: str | None = None
    resolved_layout_id: str
    visibility: Literal["visible", "hidden"] = "visible"
    boundary_action: BoundaryAction
    requested_layout_action: LayoutAction
    resolved_layout_action: LayoutAction
    override_reason: str | None = None
    transition: TransitionConfig = Field(exclude=True)


class DirectorTimelineRecord(BaseModel):
    actions: list[DirectorTimelineAction]
    resolved: list[ResolvedTimelineItem]
