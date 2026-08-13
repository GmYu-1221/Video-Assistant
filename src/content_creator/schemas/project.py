from typing import Literal
from pydantic import BaseModel, Field
from .transition import TransitionConfig
from .color import RGBColor
from .animation_plan import AnimationEffect
from .transition_effect_plan import TransitionEffectPlanItem
from .remotion_creative_plan import VisualEvent
from .visual_spec import VisualSpec


class EntranceConfig(BaseModel):
    type: str = "fade"
    durationInFrames: int = Field(default=15, ge=1)


class ImageAsset(BaseModel):
    id: str
    filename: str
    relative_path: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    backgroundColor: RGBColor = Field(default_factory=lambda: RGBColor(r=17, g=24, b=39))
    fit: Literal["contain"] = "contain"
    duration_frames: int = Field(default=1, ge=1)
    motion: str = "static"
    entrance: EntranceConfig = Field(default_factory=EntranceConfig)


class AudioConfig(BaseModel):
    path: str
    source_path: str | None = None
    duration: float = Field(ge=0)
    sample_rate: int = Field(gt=0)
    bpm: float = Field(default=120.0, gt=0)


class TimelineItem(BaseModel):
    asset_id: str
    start_frame: int = Field(ge=0)
    end_frame: int = Field(gt=0)
    duration_frames: int = Field(gt=0)
    transition: TransitionConfig
    animation: AnimationEffect | None = None
    transition_effect: TransitionEffectPlanItem | None = None
    visual_events: list[VisualEvent] = Field(default_factory=list)


class VideoOutput(BaseModel):
    project_dir: str
    render_data: str
    final_video: str


class VideoProject(BaseModel):
    project_id: str
    fps: int = Field(default=30, gt=0)
    width: int = Field(default=1920, gt=0)
    height: int = Field(default=1080, gt=0)
    images: list[ImageAsset] = Field(min_length=1)
    audio: AudioConfig
    timeline: list[TimelineItem] = Field(min_length=1)
    output: VideoOutput
    visual_spec: VisualSpec | None = None
