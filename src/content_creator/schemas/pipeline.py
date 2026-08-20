from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, computed_field, model_validator


class SourceReference(BaseModel):
    source_id: str = Field(pattern=r"^source-\d{3}$")
    paragraph_index: int = Field(ge=0)


class Material(BaseModel):
    id: str
    source_id: str
    path: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    alt: str = ""
    caption: str = ""


class SourceResult(BaseModel):
    source_id: str = Field(pattern=r"^source-\d{3}$")
    url: str
    title: str
    body: str
    summary: str = ""
    materials: list[Material] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class SourceResults(BaseModel):
    sources: list[SourceResult] = Field(min_length=1, max_length=3)


class EditorialBeat(BaseModel):
    id: str
    purpose: Literal["hook", "context", "explanation", "evidence", "conclusion"]
    point: str
    source_references: list[SourceReference] = Field(min_length=1)
    priority: int = Field(ge=1, le=10)


class EditorialPlan(BaseModel):
    thesis: str
    audience: str
    narrative: str
    title_direction: str
    mood: str = "informative"
    topics: list[str] = Field(default_factory=list, max_length=12)
    beats: list[EditorialBeat] = Field(min_length=1, max_length=12)


class CopyScene(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str
    title: str = Field(max_length=40)
    body: str = Field(max_length=180)
    emphasis: str = Field(default="", max_length=40)
    source_references: list[SourceReference] = Field(min_length=1)


class ViralCopyPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    final_title: str = Field(min_length=2, max_length=60)
    hook: str = Field(min_length=2, max_length=80)
    scenes: list[CopyScene] = Field(min_length=1, max_length=12)
    closing: str = Field(default="", max_length=80)


class SceneTiming(BaseModel):
    scene_id: str
    start_frame: int = Field(ge=0)
    end_frame: int = Field(gt=0)
    text_budget: int = Field(gt=0)

    @model_validator(mode="after")
    def valid_range(self):
        if self.end_frame <= self.start_frame:
            raise ValueError("end_frame must be greater than start_frame")
        return self


class TimingPlan(BaseModel):
    fps: int = Field(default=30, gt=0, le=60)
    duration_frames: int = Field(gt=0)
    speaking_chars_per_second: float = Field(default=7.0, gt=0)
    scenes: list[SceneTiming] = Field(min_length=1)

    @model_validator(mode="after")
    def continuous_timeline(self):
        if self.scenes[0].start_frame != 0:
            raise ValueError(f"scene {self.scenes[0].scene_id} must start at frame 0, got {self.scenes[0].start_frame}")
        for left, right in zip(self.scenes, self.scenes[1:]):
            if left.end_frame != right.start_frame:
                raise ValueError(
                    f"timing break between {left.scene_id} end_frame={left.end_frame} "
                    f"and {right.scene_id} start_frame={right.start_frame}"
                )
        if self.scenes[-1].end_frame != self.duration_frames:
            raise ValueError(
                f"scene {self.scenes[-1].scene_id} ends at {self.scenes[-1].end_frame}, "
                f"expected duration_frames={self.duration_frames}"
            )
        return self


class DirectorScene(BaseModel):
    scene_id: str
    material_ids: list[str] = Field(min_length=1)
    duration_weight: float = Field(gt=0)
    image_intent: str
    camera_intent: str
    transition_intent: str
    information_hierarchy: str
    visual_density: Literal["low", "medium", "high"] = "medium"


class CopyFitDecision(BaseModel):
    status: Literal["accepted", "revise"]
    feedback: str = ""
    scene_targets: dict[str, int] = Field(default_factory=dict)


class DirectorPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    width: int = Field(default=1080, gt=0)
    height: int = Field(default=1920, gt=0)
    fps: int = Field(default=30, gt=0)
    duration_seconds: int = Field(ge=15, le=90)
    duration_reason: str = Field(min_length=1)
    safe_area: str
    background_atmosphere: str
    typography_hierarchy: str
    alignment_tendency: str
    rhythm: str
    scenes: list[DirectorScene] = Field(min_length=1)

    @computed_field(return_type=int)
    @property
    def duration_frames(self) -> int:
        """Derived by Python; it is deliberately absent from model input schema."""
        return self.duration_seconds * self.fps

    @model_validator(mode="after")
    def unique_scene_ids(self):
        ids = [scene.scene_id for scene in self.scenes]
        if len(ids) != len(set(ids)):
            raise ValueError("Director scene IDs must be unique")
        return self


class ProjectContext(BaseModel):
    project_id: str
    project_dir: str
    urls: list[str] = Field(min_length=1, max_length=3)
    imported_html: dict[str, str] = Field(default_factory=dict)
    width: int = 1080
    height: int = 1920
    fps: int = 30
    max_copy_revision: int = 2


class AnimationArtifact(BaseModel):
    html_path: str
    model: str
    gsap_version: Literal["3.15.0"] = "3.15.0"
    width: int
    height: int
    fps: int
    duration_frames: int
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    materials: list[str] = Field(default_factory=list)
    fonts: list[str] = Field(default_factory=list)
    prompt_path: str
    artifact_metadata: dict = Field(default_factory=dict)
