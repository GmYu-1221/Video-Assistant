"""Strict DTOs used only at structured Agent boundaries."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from .article import ImageRole


class StrictAgentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class NormalizedBBoxDecision(StrictAgentModel):
    """Unambiguous Agent-facing rectangle; domain models keep using tuples."""

    x: float = Field(ge=0, le=1, description="Normalized left edge in the 0..1 image coordinate space.")
    y: float = Field(ge=0, le=1, description="Normalized top edge in the 0..1 image coordinate space.")
    width: float = Field(gt=0, le=1, description="Normalized rectangle width, not the right-edge coordinate.")
    height: float = Field(gt=0, le=1, description="Normalized rectangle height, not the bottom-edge coordinate.")

    @model_validator(mode="after")
    def inside_image(self):
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("normalized bbox must remain inside the image")
        return self


def _headline_bbox_matches_flag(value: NormalizedBBoxDecision | None, info: ValidationInfo):
    prominent = info.data.get("contains_prominent_headline")
    if prominent is True and value is None:
        raise ValueError("headline_bbox is required when contains_prominent_headline is true")
    if prominent is False and value is not None:
        raise ValueError("headline_bbox must be null when contains_prominent_headline is false")
    return value


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
    headline_bbox: NormalizedBBoxDecision | None = Field(
        description="Normalized {x,y,width,height}; never pixels, 0..1000 coordinates, an array, or x1/y1/x2/y2 endpoints."
    )
    headline_readability: float = Field(ge=0, le=1)
    eligible: bool
    exclusion_reason: str = Field(max_length=400)

    _validate_headline_bbox = field_validator("headline_bbox")(_headline_bbox_matches_flag)


class CandidateVisualAnalysisDecision(StrictAgentModel):
    candidate_profiles: list[CandidateVisualProfileDecision] = Field(min_length=1, max_length=6)


class ImageHeadlineDecision(StrictAgentModel):
    image_id: str = Field(min_length=1, max_length=80)
    contains_prominent_headline: bool
    embedded_headline_text: str = Field(max_length=500)
    headline_prominence: float = Field(ge=0, le=1)
    headline_title_match_score: float = Field(ge=0, le=1)
    headline_bbox: NormalizedBBoxDecision | None = Field(
        description="Normalized {x,y,width,height}; never pixels, 0..1000 coordinates, an array, or x1/y1/x2/y2 endpoints."
    )
    headline_readability: float = Field(ge=0, le=1)
    headline_exclusion_reason: str = Field(max_length=300)

    _validate_headline_bbox = field_validator("headline_bbox")(_headline_bbox_matches_flag)


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
    headline_bbox: NormalizedBBoxDecision | None = Field(
        description="Normalized {x,y,width,height}; never pixels, 0..1000 coordinates, an array, or x1/y1/x2/y2 endpoints."
    )
    headline_readability: float = Field(ge=0, le=1)
    headline_exclusion_reason: str = Field(max_length=300)

    _validate_headline_bbox = field_validator("headline_bbox")(_headline_bbox_matches_flag)


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
    # The key is required by StrictAgentModel; [] explicitly means no visible text.
    text_layouts: list["DirectorTextLayoutDecision"] = Field(min_length=0, max_length=5)


class DirectorTextLayoutDecision(StrictAgentModel):
    field: Literal["hook", "title", "body", "emphasis", "closing"]
    typography_profile: Literal["display", "headline", "body", "label"]
    visibility_profile: Literal["brief", "standard", "persistent"]
    hierarchy_level: Literal["primary", "secondary", "supporting"]


class DirectorDecision(StrictAgentModel):
    duration_seconds: int = Field(ge=15, le=90)
    duration_reason: str = Field(min_length=1, max_length=1000)
    safe_area: str = Field(min_length=1, max_length=1000)
    background_atmosphere: str = Field(min_length=1, max_length=1000)
    typography_hierarchy: str = Field(min_length=1, max_length=1000)
    alignment_tendency: str = Field(min_length=1, max_length=1000)
    rhythm: str = Field(min_length=1, max_length=1000)
    scenes: list[DirectorSceneDecision] = Field(min_length=1, max_length=12)


class ViralCopyPageTextDecision(StrictAgentModel):
    field: Literal["hook", "title", "body", "emphasis", "closing"]
    text: str = Field(min_length=1, max_length=2000)


class ViralCopyPageDecision(StrictAgentModel):
    material_id: str = Field(min_length=1, max_length=80)
    texts: list[ViralCopyPageTextDecision] = Field(min_length=0, max_length=5)
    source_references: list[AgentSourceReference] = Field(min_length=1, max_length=12)


class ViralCopySceneDecision(StrictAgentModel):
    scene_id: str = Field(min_length=1, max_length=80)
    pages: list[ViralCopyPageDecision] = Field(min_length=1, max_length=12)


class ViralCopyDecision(StrictAgentModel):
    final_title: str = Field(min_length=2, max_length=60)
    scenes: list[ViralCopySceneDecision] = Field(min_length=1, max_length=12)


class CopyFitPageTargetDecision(StrictAgentModel):
    scene_id: str = Field(min_length=1, max_length=80)
    page_index: int = Field(ge=0, le=11)
    field: Literal["hook", "title", "body", "emphasis", "closing"]
    action: Literal["paginate", "compress"]
    max_display_units: float | None


class SceneSplitTargetDecision(StrictAgentModel):
    scene_id: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=1, max_length=1000)
    narrative_nodes: list[str] = Field(min_length=2, max_length=6)


class CopyFitReviewDecision(StrictAgentModel):
    status: Literal["accepted", "revise_copy", "split_scene"]
    feedback: str = Field(max_length=2000)
    page_targets: list[CopyFitPageTargetDecision] = Field(min_length=0, max_length=12)
    split_targets: list[SceneSplitTargetDecision] = Field(min_length=0, max_length=12)
