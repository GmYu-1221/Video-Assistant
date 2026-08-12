from pydantic import BaseModel, Field
from .scene_plan import ScenePlan

class Storyboard(BaseModel):
    style: str = "minimal"
    scenes: list[ScenePlan] = Field(min_length=1)
