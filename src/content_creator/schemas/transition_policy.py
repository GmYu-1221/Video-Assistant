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
    "cinematic": [TransitionType.crossfade, TransitionType.black_flash, TransitionType.iris, TransitionType.light_leak],
    "modern": [TransitionType.fade, TransitionType.crossfade, TransitionType.slide_left, TransitionType.digital_wipe],
    "minimal": [TransitionType.fade, TransitionType.crossfade, TransitionType.push],
    "dynamic": [TransitionType.push, TransitionType.whip, TransitionType.digital_wipe, TransitionType.white_flash],
    "social_media": [TransitionType.whip, TransitionType.pixel_reveal, TransitionType.white_flash, TransitionType.push],
    "tech": [TransitionType.glitch, TransitionType.digital_wipe, TransitionType.pixel_reveal, TransitionType.clock_wipe],
    "news": [TransitionType.push, TransitionType.digital_wipe, TransitionType.crossfade],
    "documentary": [TransitionType.crossfade, TransitionType.black_flash, TransitionType.iris],
}
