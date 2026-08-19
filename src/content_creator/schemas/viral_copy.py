from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ViralTitleCandidate(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=2, max_length=120)
    strategy: str = Field(min_length=1, max_length=80)
    accuracy_score: float = Field(ge=0, le=1)
    clarity_score: float = Field(ge=0, le=1)
    attraction_score: float = Field(ge=0, le=1)
    image_match_score: float = Field(default=0.5, ge=0, le=1)
    source_paragraph_indices: list[int] = Field(default_factory=list, max_length=8)

    @property
    def ranking_score(self) -> float:
        return (
            self.accuracy_score * 0.45
            + self.clarity_score * 0.25
            + self.attraction_score * 0.20
            + self.image_match_score * 0.10
        )


class ViralCopyUnit(BaseModel):
    semantic_unit_id: str = Field(min_length=1, max_length=80)
    content_id: str = Field(min_length=1, max_length=80)
    purpose: Literal["opening", "explanation", "evidence", "conclusion"]
    full: str = Field(min_length=1, max_length=800)
    short: str = Field(min_length=1, max_length=400)
    micro: str = Field(min_length=1, max_length=180)
    origin: Literal["source_rewrite", "creative"] = "source_rewrite"
    source_paragraph_indices: list[int] = Field(default_factory=list, max_length=8)
    source_hash: str = Field(default="", pattern=r"^$|^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def variants_have_real_length_gradient(self):
        if not (len(self.full) > len(self.short) > len(self.micro)):
            raise ValueError("viral copy variants must satisfy full > short > micro")
        return self


class ViralCopyPlan(BaseModel):
    platform: Literal["douyin_short_video"] = "douyin_short_video"
    source_article_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    title_candidates: list[ViralTitleCandidate] = Field(min_length=5, max_length=5)
    selected_title_id: str = Field(min_length=1, max_length=80)
    final_title: str = Field(default="", max_length=120)
    caption_title_lines: list[str] = Field(default_factory=list, max_length=3)
    global_summary: str = Field(default="", max_length=140)
    content_units: list[ViralCopyUnit] = Field(min_length=1, max_length=24)

    @model_validator(mode="after")
    def references_are_unique_and_valid(self):
        title_ids = [item.candidate_id for item in self.title_candidates]
        title_texts = [item.text for item in self.title_candidates]
        if len(title_ids) != len(set(title_ids)) or len(title_texts) != len(set(title_texts)):
            raise ValueError("viral title candidates must be unique")
        if self.selected_title_id not in set(title_ids):
            raise ValueError("selected_title_id must reference a title candidate")
        if self.caption_title_lines and len(self.caption_title_lines) != 3:
            raise ValueError("caption_title_lines must contain exactly three lines")
        unit_ids = [item.semantic_unit_id for item in self.content_units]
        content_ids = [item.content_id for item in self.content_units]
        if len(unit_ids) != len(set(unit_ids)) or len(content_ids) != len(set(content_ids)):
            raise ValueError("viral copy unit IDs must be unique")
        return self

    @property
    def selected_title(self) -> ViralTitleCandidate:
        return next(item for item in self.title_candidates if item.candidate_id == self.selected_title_id)
