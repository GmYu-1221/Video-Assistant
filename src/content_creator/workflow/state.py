from __future__ import annotations

from typing import TypedDict

from content_creator.schemas import (
    AnimationArtifact, CopyFitDecision, DirectorPlan, EditorialPlan, ProjectContext,
    PresentationPlan, SourceResults, TimingPlan, ViralCopyPlan,
)


class VideoState(TypedDict, total=False):
    project: ProjectContext
    source_results: SourceResults
    editorial_plan: EditorialPlan
    viral_copy_plan: ViralCopyPlan
    timing_plan: TimingPlan
    presentation_plan: PresentationPlan
    director_plan: DirectorPlan
    copy_fit_decision: CopyFitDecision | None
    scene_split_request: CopyFitDecision | None
    animation_artifact: AnimationArtifact
    video_path: str
    errors: list[str]
    revision_count: int
    scene_split_count: int
