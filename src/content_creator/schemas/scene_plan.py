from typing import Literal

from pydantic import BaseModel, Field
from .transition import TransitionConfig
from .creative_intent import CreativeIntent
from .layout import SceneNarrative, SceneLayoutSpec

class EntrancePlan(BaseModel):
    type: Literal["none", "fade_scale", "slide_up"] = "none"
    durationInFrames: int = Field(default=15, ge=1)

class MotionPlan(BaseModel):
    type: str = "static"

class ScenePlan(BaseModel):
    scene_id: str
    asset_id: str
    duration_frames: int = Field(gt=0)
    entrance: EntrancePlan = Field(default_factory=EntrancePlan)
    motion: MotionPlan = Field(default_factory=MotionPlan)
    transition: TransitionConfig = Field(default_factory=TransitionConfig)
    emotion: str = "neutral"
    creative_intent: CreativeIntent | None = None
    transition_intent: CreativeIntent | None = None
    timing: str | None = None
    narrative: SceneNarrative | None = None
    layout: SceneLayoutSpec | None = None
