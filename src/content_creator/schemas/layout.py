"""Renderer-safe, content-driven scene layout protocol.

The protocol deliberately carries geometry and semantic tokens only.  It is
interpreted by the shared Remotion renderer; no agent supplied CSS or TSX is
ever executed.
"""
from __future__ import annotations

from enum import Enum
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920


class TypographyRole(str, Enum):
    display = "display"
    headline = "headline"
    body = "body"
    caption = "caption"
    metadata = "metadata"
    quote = "quote"
    numeric = "numeric"


class StyleIntent(str, Enum):
    modern_sans = "modern_sans"
    readable_serif = "readable_serif"
    handwritten = "handwritten"
    display = "display"
    calligraphic = "calligraphic"


class ContentVariant(str, Enum):
    full = "full"
    short = "short"
    micro = "micro"


class CopyDensityIntent(str, Enum):
    increase = "increase"
    reduce = "reduce"
    preserve = "preserve"


class TextOutline(str, Enum):
    none = "none"
    dark_thin = "dark_thin"
    dark_strong = "dark_strong"


class TextShadow(str, Enum):
    none = "none"
    soft = "soft"
    strong = "strong"


class LetterSpacing(str, Enum):
    normal = "normal"
    relaxed = "relaxed"


class CaptionStyleIntent(str, Enum):
    reference_emphasis = "reference_emphasis"
    explanatory = "explanatory"
    minimal = "minimal"


class Rect(BaseModel):
    x: int = Field(ge=0, le=CANVAS_WIDTH)
    y: int = Field(ge=0, le=CANVAS_HEIGHT)
    width: int = Field(gt=0, le=CANVAS_WIDTH)
    height: int = Field(gt=0, le=CANVAS_HEIGHT)

    @model_validator(mode="after")
    def inside_canvas(self) -> "Rect":
        if self.x + self.width > CANVAS_WIDTH or self.y + self.height > CANVAS_HEIGHT:
            raise ValueError("bbox must be inside the 1080x1920 canvas")
        return self


class ImageSemanticProfile(BaseModel):
    role: str = "other"
    narrative_function: str = "context"
    contains_text: bool | None = None
    is_screenshot: bool | None = None
    is_data_chart: bool | None = None
    importance: float = Field(default=.5, ge=0, le=1)
    information_density: float = Field(default=.5, ge=0, le=1)
    source_caption: str = ""
    generated_description: str = ""
    focal_point: tuple[float, float] | None = None
    subject_bbox: Rect | None = None
    safe_text_regions: list[Rect] | None = None
    contains_prominent_headline: bool | None = None
    embedded_headline_text: str = Field(default="", max_length=500)
    headline_prominence: float = Field(default=0.0, ge=0, le=1)
    headline_title_match_score: float = Field(default=0.0, ge=0, le=1)
    headline_bbox: tuple[float, float, float, float] | None = None
    headline_readability: float = Field(default=0.0, ge=0, le=1)
    headline_analysis_status: Literal["verified", "unavailable", "failed"] = "unavailable"
    headline_exclusion_reason: str = Field(default="", max_length=300)

    @field_validator("headline_bbox")
    @classmethod
    def normalized_headline_bbox(cls, value):
        if value is not None and (any(item < 0 or item > 1 for item in value) or value[2] <= 0 or value[3] <= 0 or value[0] + value[2] > 1 or value[1] + value[3] > 1):
            raise ValueError("headline_bbox must be normalized x,y,width,height inside the image")
        return value


class NarrativeContent(BaseModel):
    semantic_unit_id: str = Field(min_length=1, max_length=80)
    content_id: str = Field(min_length=1, max_length=80)
    full: str = Field(min_length=1, max_length=800)
    short: str = Field(min_length=1, max_length=400)
    micro: str = Field(min_length=1, max_length=180)
    source_kind: Literal["title", "summary", "body", "existing", "generated"] = "existing"
    source_index: int | None = Field(default=None, ge=0)
    source_hash: str = Field(default="", pattern=r"^$|^[0-9a-f]{64}$")

    def value(self, variant: ContentVariant) -> str:
        return getattr(self, variant.value)

    def content_hash(self, variant: ContentVariant) -> str:
        return sha256(self.value(variant).encode("utf-8")).hexdigest()

    def variant_id(self, variant: ContentVariant) -> str:
        return f"{self.semantic_unit_id}:{variant.value}"


class SceneNarrative(BaseModel):
    copy_id: str
    scene_id: str
    asset_id: str
    scene_purpose: str
    contents: list[NarrativeContent] = Field(min_length=1, max_length=4)


class BackgroundTreatment(BaseModel):
    color: str = Field(default="#0B0D10", pattern=r"^#[0-9A-Fa-f]{6}$")
    media_blur: int = Field(default=0, ge=0, le=40)
    overlay_opacity: float = Field(default=0, ge=0, le=.85)


class MediaBlock(BaseModel):
    block_id: str = Field(min_length=1, max_length=80)
    asset_id: str
    bbox: Rect
    fit: Literal["contain", "cover"] = "cover"
    focal_point: tuple[float, float] | None = None
    border_radius: int = Field(default=0, ge=0, le=48)
    z_index: int = Field(default=1, ge=0, le=20)
    full_bleed: bool = False


class TextBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    block_id: str = Field(min_length=1, max_length=80)
    content_id: str
    semantic_unit_id: str
    variant_id: ContentVariant = ContentVariant.full
    content_hash: str = Field(min_length=64, max_length=64)
    bbox: Rect
    alignment: Literal["left", "center", "right"] = "left"
    typography_role: TypographyRole
    font_id: str = Field(default="noto-sans-sc", min_length=1, max_length=80)
    style_intent: StyleIntent = StyleIntent.modern_sans
    weight: Literal["regular", "medium", "bold"] = "regular"
    color: str = Field(default="#FFFFFF", pattern=r"^#[0-9A-Fa-f]{6}$")
    max_lines: int = Field(ge=1, le=8)
    emphasis: list[str] = Field(default_factory=list, max_length=4)
    emphasis_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    outline: TextOutline = TextOutline.none
    shadow: TextShadow = TextShadow.none
    letter_spacing: LetterSpacing = LetterSpacing.normal
    caption_style_intent: CaptionStyleIntent = CaptionStyleIntent.explanatory
    z_index: int = Field(default=2, ge=0, le=20)

    @model_validator(mode="after")
    def registered_font_is_compatible(self) -> "TextBlock":
        from content_creator.font_registry import validate_font_for_role

        validate_font_for_role(self.font_id, self.typography_role.value)
        return self


class PersistentTitleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=500)
    content_hash: str = Field(min_length=64, max_length=64)
    bbox: Rect = Field(default_factory=lambda: Rect(x=60, y=80, width=960, height=280))
    alignment: Literal["left", "center", "right"] = "left"
    typography_role: Literal[TypographyRole.headline] = TypographyRole.headline
    font_id: str = Field(default="noto-sans-sc", min_length=1, max_length=80)
    style_intent: StyleIntent = StyleIntent.modern_sans
    weight: Literal["regular", "medium", "bold"] = "bold"
    color: str = Field(default="#DCE74A", pattern=r"^#[0-9A-Fa-f]{6}$")
    outline: TextOutline = TextOutline.dark_strong
    shadow: TextShadow = TextShadow.strong
    letter_spacing: LetterSpacing = LetterSpacing.normal
    caption_style_intent: Literal[CaptionStyleIntent.reference_emphasis] = CaptionStyleIntent.reference_emphasis
    max_lines: Literal[3] = 3
    entrance_duration_frames: int = Field(default=12, ge=1, le=30)
    z_index: int = Field(default=30, ge=21, le=40)

    @model_validator(mode="after")
    def validate_frozen_title(self) -> "PersistentTitleSpec":
        from content_creator.font_registry import validate_font_for_role

        if self.bbox != Rect(x=60, y=80, width=960, height=280):
            raise ValueError("persistent title must use the fixed top region")
        if self.content_hash != sha256(self.content.encode("utf-8")).hexdigest():
            raise ValueError("persistent title content hash mismatch")
        validate_font_for_role(self.font_id, TypographyRole.headline.value)
        return self


class OverlayPolicy(BaseModel):
    allowed_pairs: list[tuple[str, str]] = Field(default_factory=list, max_length=8)
    reason: str = Field(default="", max_length=240)


class SceneLayoutSpec(BaseModel):
    layout_id: str
    parent_layout_id: str | None = None
    change_mode: Literal["root", "adapt", "replace"] = "root"
    changed_block_ids: list[str] = Field(default_factory=list)
    scene_id: str
    background: BackgroundTreatment = Field(default_factory=BackgroundTreatment)
    media_blocks: list[MediaBlock] = Field(min_length=1, max_length=3)
    text_blocks: list[TextBlock] = Field(default_factory=list, max_length=4)
    overlay_policy: OverlayPolicy = Field(default_factory=OverlayPolicy)
    minimal_scene: bool = False


class LayoutPlan(BaseModel):
    version: Literal["1.0"] = "1.0"
    canvas_width: Literal[1080] = CANVAS_WIDTH
    canvas_height: Literal[1920] = CANVAS_HEIGHT
    global_style: str = "editorial"
    persistent_title: PersistentTitleSpec | None = None
    scenes: list[SceneLayoutSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def limit_font_palette(self) -> "LayoutPlan":
        font_ids = {block.font_id for scene in self.scenes for block in scene.text_blocks}
        if len(font_ids) > 2:
            raise ValueError("a video layout may use at most two registered fonts")
        return self


class LayoutIssue(BaseModel):
    code: str
    severity: Literal["info", "warning", "error", "critical"] = "error"
    block_id: str | None = None
    message: str
    repair_hint: str = ""


class RenderedLayoutValidationResult(BaseModel):
    scene_id: str
    fonts_ready: bool = False
    font_families: list[str] = Field(default_factory=list)
    blocks: dict[str, dict] = Field(default_factory=dict)
    issues: list[LayoutIssue] = Field(default_factory=list)
    passed: bool = False


class VisualCriticResult(BaseModel):
    passed: bool
    quality_score: float = Field(ge=0, le=1)
    issues: list[LayoutIssue] = Field(default_factory=list)
    mode: Literal["multimodal", "critic_unavailable"] = "critic_unavailable"
    error: str | None = None
