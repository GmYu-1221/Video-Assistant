"""Validated records for URL-sourced video projects."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, HttpUrl


class ImageRole(str, Enum):
    hero = "hero"
    overview = "overview"
    evidence = "evidence"
    data = "data"
    diagram = "diagram"
    demo = "demo"
    product = "product"
    quote = "quote"
    result = "result"
    brand = "brand"
    portrait = "portrait"
    other = "other"
    irrelevant = "irrelevant"


class AssetKind(str, Enum):
    image = "image"
    video = "video"
    embedded_video = "embedded_video"


class TransitionRelation(str, Enum):
    continuation = "continuation"
    detail = "detail"
    contrast = "contrast"
    evidence = "evidence"
    climax = "climax"


class ArticleBrief(BaseModel):
    # `url` is kept for compatibility with existing projects. The explicit
    # fields preserve the submitted URL identity separately from page hints.
    url: str = Field(min_length=1, max_length=2048)
    requested_url: str = Field(default="", max_length=2048)
    canonical_url: str = Field(min_length=1, max_length=2048)
    effective_base_url: str = Field(default="", max_length=2048)
    site_name: str = Field(default="", max_length=160)
    author: str = Field(default="", max_length=160)
    published_at: str = Field(default="", max_length=80)
    title: str = Field(min_length=1, max_length=500)
    text: str = Field(min_length=1, max_length=50000)
    summary: str = Field(default="", max_length=1200)
    topics: list[str] = Field(default_factory=list, max_length=12)
    mood: str = Field(default="informative", max_length=40)


class ArticleTextCandidate(BaseModel):
    id: str
    source: str
    selector_or_key: str = ""
    text: str = ""
    html: str = ""
    title_context: str = ""
    section_index: int = Field(default=0, ge=0)
    char_count: int = Field(default=0, ge=0)
    paragraph_count: int = Field(default=0, ge=0)
    image_count: int = Field(default=0, ge=0)
    duplicate_group: str | None = None


class CandidatePreview(BaseModel):
    id: str
    source: str
    selector_or_key: str = ""
    char_count: int = Field(default=0, ge=0)
    paragraph_count: int = Field(default=0, ge=0)
    image_count: int = Field(default=0, ge=0)
    title_context: str = ""
    beginning: str = ""
    middle: str = ""
    ending: str = ""


class ArticleExtractionResult(BaseModel):
    requested_url: str
    canonical_url: str
    effective_base_url: str
    extraction_method: str
    extraction_confidence: float = Field(default=0.0, ge=0, le=1)
    selected_candidate_ids: list[str] = Field(default_factory=list)
    title: str
    body: str
    selected_html: str = ""
    diagnostics: dict = Field(default_factory=dict)


class ArticleImage(BaseModel):
    id: str
    source_url: str = Field(min_length=1, max_length=2048)
    local_path: str = Field(min_length=1)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    source_index: int = Field(ge=0)
    alt: str = Field(default="", max_length=600)
    caption: str = Field(default="", max_length=1000)
    context: str = Field(default="", max_length=2000)
    sha256: str = Field(min_length=16, max_length=64)


class AssetCandidate(BaseModel):
    id: str
    kind: AssetKind
    source_url: str = Field(min_length=1, max_length=2048)
    page_url: str = Field(min_length=1, max_length=2048)
    section_index: int = Field(default=0, ge=0)
    original_index: int = Field(default=0, ge=0)
    source_types: list[str] = Field(default_factory=list, max_length=8)
    alt: str = Field(default="", max_length=600)
    caption: str = Field(default="", max_length=1000)
    nearby_text: str = Field(default="", max_length=2000)
    mime_type: str = Field(default="", max_length=120)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    duration: float | None = Field(default=None, gt=0)
    is_svg: bool = False


class AssetDecision(BaseModel):
    asset_id: str
    selected: bool = False
    role: ImageRole = ImageRole.other
    topics: list[str] = Field(default_factory=list, max_length=8)
    entities: list[str] = Field(default_factory=list, max_length=12)
    relevance: float = Field(default=0.0, ge=0, le=1)
    visual_quality: float = Field(default=0.5, ge=0, le=1)
    reason: str = Field(default="", max_length=400)


class ImageTag(BaseModel):
    image_id: str
    role: ImageRole = ImageRole.other
    topics: list[str] = Field(default_factory=list, max_length=8)
    entities: list[str] = Field(default_factory=list, max_length=12)
    salience: float = Field(default=0.5, ge=0, le=1)
    visual_quality: float = Field(default=0.5, ge=0, le=1)
    section_index: int = Field(default=0, ge=0)


class TransitionContext(BaseModel):
    from_image_id: str
    to_image_id: str
    relation: TransitionRelation
    strength: float = Field(default=0.5, ge=0, le=1)
    reason: str = Field(default="", max_length=240)


class MusicTrack(BaseModel):
    id: str
    path: str
    moods: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    energy: float = Field(default=0.5, ge=0, le=1)
    bpm: float | None = Field(default=None, gt=0)
    license_note: str = Field(default="", max_length=300)
