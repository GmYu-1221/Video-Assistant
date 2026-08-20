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


TextFieldName = Literal["hook", "title", "body", "emphasis", "closing"]


class CopyPageText(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: TextFieldName
    # The generous schema ceiling lets semantic validation request pagination.
    text: str = Field(min_length=1, max_length=2000)


class CopyPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_id: str
    material_id: str
    texts: list[CopyPageText] = Field(max_length=5)
    source_references: list[SourceReference] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def unique_text_fields(self):
        fields = [item.field for item in self.texts]
        if len(fields) != len(set(fields)):
            raise ValueError("Copy page text fields must be unique")
        return self


class CopyScene(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str
    pages: list[CopyPage] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def unique_page_ids(self):
        ids = [page.page_id for page in self.pages]
        if len(ids) != len(set(ids)):
            raise ValueError("Copy page IDs must be unique within a scene")
        return self


class ViralCopyPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    final_title: str = Field(min_length=2, max_length=60)
    scenes: list[CopyScene] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def unique_scene_ids(self):
        ids = [scene.scene_id for scene in self.scenes]
        if len(ids) != len(set(ids)):
            raise ValueError("Copy scene IDs must be unique")
        return self
TypographyProfile = Literal["display", "headline", "body", "label"]
VisibilityProfile = Literal["brief", "standard", "persistent"]
HierarchyLevel = Literal["primary", "secondary", "supporting"]


class DirectorTextLayout(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: TextFieldName
    typography_profile: TypographyProfile
    visibility_profile: VisibilityProfile
    hierarchy_level: HierarchyLevel


class TextFieldBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: TextFieldName
    typography_profile: TypographyProfile
    visibility_profile: VisibilityProfile
    hierarchy_level: HierarchyLevel
    font_size_px: int = Field(gt=0)
    max_lines: int = Field(gt=0)
    max_units_per_line: float = Field(gt=0)
    min_visible_frames: int = Field(gt=0)
    max_total_units: float = Field(gt=0, multiple_of=0.5)


class SceneTiming(BaseModel):
    scene_id: str
    start_frame: int = Field(ge=0)
    end_frame: int = Field(gt=0)
    field_budgets: list[TextFieldBudget] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_range(self):
        if self.end_frame <= self.start_frame:
            raise ValueError("end_frame must be greater than start_frame")
        return self


class TimingPlan(BaseModel):
    fps: int = Field(default=30, gt=0, le=60)
    duration_frames: int = Field(gt=0)
    base_reading_units_per_second: float = Field(default=10.0, gt=0)
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


class PresentationPageTiming(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_id: str
    material_id: str
    start_frame: int = Field(ge=0)
    end_frame: int = Field(gt=0)
    field_budgets: list[TextFieldBudget] = Field(max_length=5)

    @model_validator(mode="after")
    def valid_range(self):
        if self.end_frame <= self.start_frame:
            raise ValueError("page end_frame must be greater than start_frame")
        return self


class PresentationScene(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str
    start_frame: int = Field(ge=0)
    end_frame: int = Field(gt=0)
    pages: list[PresentationPageTiming] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def continuous_pages(self):
        if self.pages[0].start_frame != self.start_frame:
            raise ValueError(f"scene {self.scene_id} first page must start at {self.start_frame}")
        for left, right in zip(self.pages, self.pages[1:]):
            if left.end_frame != right.start_frame:
                raise ValueError(f"page timing break between {left.page_id} and {right.page_id}")
        if self.pages[-1].end_frame != self.end_frame:
            raise ValueError(f"scene {self.scene_id} last page must end at {self.end_frame}")
        return self


class PresentationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fps: int = Field(gt=0, le=60)
    duration_frames: int = Field(gt=0)
    scenes: list[PresentationScene] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def continuous_scenes(self):
        if self.scenes[0].start_frame != 0:
            raise ValueError("PresentationPlan must start at frame 0")
        for left, right in zip(self.scenes, self.scenes[1:]):
            if left.end_frame != right.start_frame:
                raise ValueError(f"presentation timing break between {left.scene_id} and {right.scene_id}")
        if self.scenes[-1].end_frame != self.duration_frames:
            raise ValueError("PresentationPlan must end at duration_frames")
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
    # Required in the Agent contract, but may be [] for a genuinely text-free scene.
    text_layouts: list[DirectorTextLayout] = Field(max_length=5)


class CopyFitPageTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str
    page_index: int = Field(ge=0, le=11)
    field: TextFieldName
    action: Literal["paginate", "compress"]
    max_display_units: float | None = Field(default=None, gt=0, multiple_of=0.5)

    @model_validator(mode="after")
    def valid_action(self):
        if self.action == "compress" and self.max_display_units is None:
            raise ValueError("compress target requires max_display_units")
        if self.action == "paginate" and self.max_display_units is not None:
            raise ValueError("paginate target must use null max_display_units")
        return self


class SceneSplitTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str
    reason: str = Field(min_length=1)
    narrative_nodes: list[str] = Field(min_length=2, max_length=6)


class CopyFitDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["accepted", "revise_copy", "split_scene"]
    feedback: str = ""
    page_targets: list[CopyFitPageTarget] = Field(default_factory=list)
    split_targets: list[SceneSplitTarget] = Field(default_factory=list)


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
    max_scene_split: int = 1


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
