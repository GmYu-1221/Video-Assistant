from pydantic import BaseModel, Field
from .transition import TransitionType
from .transition import TransitionConfig


class TransitionPolicy(BaseModel):
    mode: str = "sequential"
    allowed: list[TransitionType] = Field(default_factory=lambda: [TransitionType.fade, TransitionType.slide_left, TransitionType.slide_right, TransitionType.wipe_left, TransitionType.zoom_in, TransitionType.zoom_blur])
    weights: dict[TransitionType, int] = Field(default_factory=dict)
    avoid_repeat: bool = True
    max_complexity: float = Field(default=1.0, ge=0, le=1)
    seed: int | None = None


class TransitionPlanItem(BaseModel):
    index: int = Field(ge=0)
    transition: TransitionConfig


class TransitionPlan(BaseModel):
    transitions: list[TransitionPlanItem]


PRESETS: dict[str, list[TransitionType]] = {
    "cinematic": [TransitionType.fade, TransitionType.dissolve, TransitionType.zoom_out, TransitionType.slide_left],
    "modern": [TransitionType.fade, TransitionType.crossfade, TransitionType.slide_left, TransitionType.wipe_right],
    "minimal": [TransitionType.fade, TransitionType.dissolve, TransitionType.slide_left],
    "dynamic": [TransitionType.zoom_in, TransitionType.push_left, TransitionType.wipe_right, TransitionType.flash],
    "social_media": [TransitionType.zoom_in, TransitionType.slide_left, TransitionType.flash, TransitionType.wipe_up],
    "tech": [TransitionType.glitch, TransitionType.digital_wipe, TransitionType.rgb_split, TransitionType.slide_right],
    "news": [TransitionType.wipe_left, TransitionType.slide_left, TransitionType.fade],
    "documentary": [TransitionType.fade, TransitionType.dissolve, TransitionType.slide_right],
}
