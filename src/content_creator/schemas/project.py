from typing import Literal
from pydantic import BaseModel, Field, field_validator
from .transition import TransitionConfig
from .color import RGBColor
from .animation_plan import AnimationEffect
from .transition_effect_plan import TransitionEffectPlanItem
from .remotion_creative_plan import VisualEvent
from .visual_spec import VisualSpec
from .layout import ImageSemanticProfile, PersistentTitleSpec, SceneLayoutSpec, SceneNarrative
from .continuity import ResolvedTimelineItem
from .caption_template import CaptionTemplatePlan


class EntranceConfig(BaseModel):
    type: Literal["none", "fade_scale", "slide_up"] = "none"
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
    semantic_profile: ImageSemanticProfile | None = None


class AudioConfig(BaseModel):
    path: str
    source_path: str | None = None
    duration: float = Field(ge=0)
    sample_rate: int = Field(gt=0)
    bpm: float = Field(default=120.0, gt=0)


class BackgroundVideoConfig(BaseModel):
    path: str = Field(min_length=1)
    source_filename: str = Field(min_length=1)
    duration: float = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fit: Literal["cover"] = "cover"
    loop: Literal[True] = True
    muted: Literal[True] = True
    overlay_opacity: float = Field(default=.62, ge=0, le=.9)


class BackgroundImageConfig(BaseModel):
    path: str = Field(min_length=1)
    source_filename: str = Field(min_length=1)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fit: Literal["cover"] = "cover"
    overlay_opacity: float = Field(default=.58, ge=0, le=.9)


class VideoCopy(BaseModel):
    """User-authored copy rendered in the persistent center-stage layout."""
    headline: str = Field(default="", max_length=80)
    subtitle: str = Field(default="", max_length=40)
    body: str = Field(default="", max_length=400)

    @field_validator("headline", "subtitle", "body")
    @classmethod
    def validate_line_count(cls, value: str, info) -> str:
        limits = {"headline": 2, "subtitle": 2, "body": 8}
        if len(value.splitlines() or [value]) > limits[info.field_name]:
            raise ValueError(f"{info.field_name} exceeds {limits[info.field_name]} lines")
        return value


class TimelineItem(BaseModel):
    asset_id: str
    start_frame: int = Field(ge=0)
    end_frame: int = Field(gt=0)
    duration_frames: int = Field(gt=0)
    transition: TransitionConfig = Field(default_factory=TransitionConfig, exclude=True)
    animation: AnimationEffect | None = None
    transition_effect: TransitionEffectPlanItem | None = None
    visual_events: list[VisualEvent] = Field(default_factory=list)
    narrative: SceneNarrative | None = None
    layout: SceneLayoutSpec | None = None
    resolved_state: ResolvedTimelineItem | None = None


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
    background_video: BackgroundVideoConfig | None = None
    background_image: BackgroundImageConfig | None = None
    timeline: list[TimelineItem] = Field(min_length=1)
    output: VideoOutput
    video_copy: VideoCopy = Field(default_factory=VideoCopy)
    persistent_title: PersistentTitleSpec | None = None
    caption_template_plan: CaptionTemplatePlan | None = None
    visual_spec: VisualSpec | None = None
