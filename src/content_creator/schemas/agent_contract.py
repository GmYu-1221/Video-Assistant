"""Strict DTOs used only at structured Agent boundaries."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .article import ImageRole


class StrictAgentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class AgentSourceReference(StrictAgentModel):
    source_id: str = Field(pattern=r"^source-\d{3}$")
    paragraph_index: int = Field(ge=0)


class ArticleSelectionDecision(StrictAgentModel):
    selected_candidate_ids: list[str] = Field(min_length=1, max_length=64)
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=400)


class ArticleTranslationRow(StrictAgentModel):
    source_index: int = Field(ge=0)
    zh_text: str = Field(min_length=1, max_length=10000)


class ArticleTranslationBatchDecision(StrictAgentModel):
    title: str = Field(max_length=500)
    summary: str = Field(max_length=1200)
    paragraphs: list[ArticleTranslationRow] = Field(min_length=1, max_length=7)


class CandidateVisualProfileDecision(StrictAgentModel):
    asset_id: str = Field(min_length=1, max_length=80)
    role: ImageRole
    topics: list[str] = Field(min_length=0, max_length=8)
    entities: list[str] = Field(min_length=0, max_length=12)
    relevance: float = Field(ge=0, le=1)
    visual_quality: float = Field(ge=0, le=1)
    title_match_score: float = Field(ge=0, le=1)
    is_qr_code: bool
    is_advertisement: bool
    is_page_ui: bool
    is_logo: bool
    is_app_download: bool
    contains_prominent_headline: bool
    embedded_headline_text: str = Field(max_length=500)
    headline_prominence: float = Field(ge=0, le=1)
    headline_bbox: tuple[float, float, float, float] | None
    headline_readability: float = Field(ge=0, le=1)
    eligible: bool
    exclusion_reason: str = Field(max_length=400)

    @field_validator("headline_bbox")
    @classmethod
    def normalized_bbox(cls, value):
        if value is not None and (
            any(item < 0 or item > 1 for item in value)
            or value[2] <= 0 or value[3] <= 0
            or value[0] + value[2] > 1 or value[1] + value[3] > 1
        ):
            raise ValueError("headline_bbox must be normalized x,y,width,height inside the image")
        return value


class CandidateVisualAnalysisDecision(StrictAgentModel):
    candidate_profiles: list[CandidateVisualProfileDecision] = Field(min_length=1, max_length=6)


class ImageHeadlineDecision(StrictAgentModel):
    image_id: str = Field(min_length=1, max_length=80)
    contains_prominent_headline: bool
    embedded_headline_text: str = Field(max_length=500)
    headline_prominence: float = Field(ge=0, le=1)
    headline_title_match_score: float = Field(ge=0, le=1)
    headline_bbox: tuple[float, float, float, float] | None
    headline_readability: float = Field(ge=0, le=1)
    headline_exclusion_reason: str = Field(max_length=300)


class ImageHeadlineBatchDecision(StrictAgentModel):
    image_headlines: list[ImageHeadlineDecision] = Field(min_length=1, max_length=4)


class VideoCopyDecision(StrictAgentModel):
    headline: str = Field(max_length=80)
    subtitle: str = Field(max_length=40)
    body: str = Field(max_length=400)


class ImageTagDecision(StrictAgentModel):
    image_id: str = Field(min_length=1, max_length=80)
    role: ImageRole
    topics: list[str] = Field(min_length=0, max_length=8)
    entities: list[str] = Field(min_length=0, max_length=12)
    salience: float = Field(ge=0, le=1)
    visual_quality: float = Field(ge=0, le=1)
    contains_prominent_headline: bool
    embedded_headline_text: str = Field(max_length=500)
    headline_prominence: float = Field(ge=0, le=1)
    headline_title_match_score: float = Field(ge=0, le=1)
    headline_bbox: tuple[float, float, float, float] | None
    headline_readability: float = Field(ge=0, le=1)
    headline_exclusion_reason: str = Field(max_length=300)


class ArticleImageTaggingDecision(StrictAgentModel):
    summary: str = Field(max_length=1200)
    topics: list[str] = Field(min_length=0, max_length=12)
    mood: str = Field(min_length=1, max_length=40)
    video_copy: VideoCopyDecision
    image_tags: list[ImageTagDecision] = Field(min_length=1, max_length=6)


class AssetDecisionItem(StrictAgentModel):
    asset_id: str = Field(min_length=1, max_length=80)
    selected: bool
    role: ImageRole
    topics: list[str] = Field(min_length=0, max_length=8)
    entities: list[str] = Field(min_length=0, max_length=12)
    relevance: float = Field(ge=0, le=1)
    visual_quality: float = Field(ge=0, le=1)
    title_match_score: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=400)


class AssetSelectionDecision(StrictAgentModel):
    asset_decisions: list[AssetDecisionItem] = Field(min_length=1, max_length=24)


class EditorialBeatDecision(StrictAgentModel):
    purpose: Literal["hook", "context", "explanation", "evidence", "conclusion"]
    point: str = Field(min_length=1, max_length=2000)
    source_references: list[AgentSourceReference] = Field(min_length=1, max_length=12)
    priority: int = Field(ge=1, le=10)


class EditorialDecision(StrictAgentModel):
    thesis: str = Field(min_length=1, max_length=2000)
    audience: str = Field(min_length=1, max_length=500)
    narrative: str = Field(min_length=1, max_length=4000)
    title_direction: str = Field(min_length=1, max_length=500)
    mood: str = Field(min_length=1, max_length=40)
    topics: list[str] = Field(min_length=0, max_length=12)
    beats: list[EditorialBeatDecision] = Field(min_length=1, max_length=12)


class DirectorSceneDecision(StrictAgentModel):
    material_ids: list[str] = Field(min_length=1, max_length=18)
    duration_weight: float = Field(gt=0)
    image_intent: str = Field(min_length=1, max_length=1000)
    camera_intent: str = Field(min_length=1, max_length=1000)
    transition_intent: str = Field(min_length=1, max_length=1000)
    information_hierarchy: str = Field(min_length=1, max_length=1000)
    visual_density: Literal["low", "medium", "high"]


class DirectorDecision(StrictAgentModel):
    duration_seconds: int = Field(ge=15, le=90)
    duration_reason: str = Field(min_length=1, max_length=1000)
    safe_area: str = Field(min_length=1, max_length=1000)
    background_atmosphere: str = Field(min_length=1, max_length=1000)
    typography_hierarchy: str = Field(min_length=1, max_length=1000)
    alignment_tendency: str = Field(min_length=1, max_length=1000)
    rhythm: str = Field(min_length=1, max_length=1000)
    scenes: list[DirectorSceneDecision] = Field(min_length=1, max_length=12)


class ViralCopySceneDecision(StrictAgentModel):
    scene_id: str = Field(min_length=1, max_length=80)
    title: str = Field(max_length=40)
    body: str = Field(max_length=180)
    emphasis: str = Field(max_length=40)
    source_references: list[AgentSourceReference] = Field(min_length=1, max_length=12)


class ViralCopyDecision(StrictAgentModel):
    final_title: str = Field(min_length=2, max_length=60)
    hook: str = Field(min_length=2, max_length=80)
    scenes: list[ViralCopySceneDecision] = Field(min_length=1, max_length=12)
    closing: str = Field(max_length=80)


class CopyFitTargetDecision(StrictAgentModel):
    scene_id: str = Field(min_length=1, max_length=80)
    max_chars: int = Field(gt=0)


class CopyFitReviewDecision(StrictAgentModel):
    status: Literal["accepted", "revise"]
    feedback: str = Field(max_length=2000)
    targets: list[CopyFitTargetDecision] = Field(min_length=0, max_length=12)
