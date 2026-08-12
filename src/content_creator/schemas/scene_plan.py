from pydantic import BaseModel, Field
from .transition import TransitionConfig

class EntrancePlan(BaseModel):
    type: str = "fade"
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
