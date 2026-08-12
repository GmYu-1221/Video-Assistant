"""Small, scene-addressed edits returned by Director Chat."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .creative_intent import CreativeIntent
from .transition import TransitionConfig


class DirectorPlanChanges(BaseModel):
    """Only the explicitly requested scene properties may be changed."""

    model_config = ConfigDict(extra="forbid")

    creative_intent: CreativeIntent | None = None
    duration_frames: int | None = Field(default=None, gt=0)
    transition: TransitionConfig | None = None
    emotion: str | None = Field(default=None, min_length=1, max_length=500)
    timing: str | None = Field(default=None, min_length=1, max_length=160)

    @model_validator(mode="after")
    def require_a_real_change(self) -> "DirectorPlanChanges":
        if not self.model_fields_set:
            raise ValueError("changes must contain at least one field")
        if "creative_intent" in self.model_fields_set and self.creative_intent is None:
            raise ValueError("creative_intent cannot be null")
        return self


class DirectorPlanPatchOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str = Field(min_length=1, max_length=120)
    changes: DirectorPlanChanges


class DirectorPlanPatch(BaseModel):
    """The complete response contract for a Director Chat update."""

    model_config = ConfigDict(extra="forbid")

    operations: list[DirectorPlanPatchOperation] = Field(min_length=1, max_length=100)
