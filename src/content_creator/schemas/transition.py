from enum import Enum
from pydantic import BaseModel, Field


class TransitionType(str, Enum):
    fade = "fade"
    slide = "slide"
    wipe = "wipe"
    flip = "flip"
    zoom_blur = "zoom_blur"


class TransitionConfig(BaseModel):
    type: TransitionType = TransitionType.fade
    duration_frames: int = Field(default=12, ge=1)
    direction: str = "from-right"
