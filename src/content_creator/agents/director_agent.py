"""Director decisions: images + beat analysis + style -> validated DirectorPlan."""

from __future__ import annotations

from content_creator.prompts.director_prompt import director_prompt
from content_creator.schemas import (
    DirectorPlan,
    DirectorTimelineItem,
    EntrancePlan,
    ImageAsset,
    MotionPlan,
    ScenePlan,
    Storyboard,
    TransitionConfig,
)
from content_creator.services.llm.provider import LLMProvider
from content_creator.services.llm.router import get_agent_provider
from content_creator.services.llm.validator import validate_director_plan_json
from content_creator.services.music.beat_detector import BeatAnalysis
from content_creator.services.timeline.slideshow_builder import ImageDurationPolicy
from content_creator.services.director.transition_policy import apply_transition_policy, build_transition_sequence, DEFAULT_DURATION


VideoStyle = str


def _fallback_plan(images: list[ImageAsset], beat_analysis: BeatAnalysis) -> DirectorPlan:
    policy = ImageDurationPolicy()
    beat_seconds = 60.0 / max(beat_analysis.bpm, 1.0)
    duration = max(1, round(policy.default_beats * beat_seconds * 30))
    strengths = beat_analysis.beat_strengths
    transitions = build_transition_sequence(len(images), strengths, seed=0)
    return DirectorPlan(
        timeline=[
            DirectorTimelineItem(
                asset_id=asset.id,
                duration_frames=duration,
                transition=TransitionConfig(type=transitions[index], duration_frames=DEFAULT_DURATION.get(transitions[index], 6)),
                transition_strength=0.5,
                motion="static",
                reason="Rule-based pacing from the BGM beat grid.",
            )
            for index, asset in enumerate(images)
        ]
    )


def create_director_plan(
    images: list[ImageAsset],
    beat_analysis: BeatAnalysis,
    style: VideoStyle,
    provider: LLMProvider | None = None,
) -> DirectorPlan:
    """Generate a strictly validated plan, with deterministic local fallback."""
    if not images:
        raise ValueError("Director Agent requires at least one image")
    fallback = _fallback_plan(images, beat_analysis)
    active_provider = provider or get_agent_provider("director")
    if active_provider.model_name == "mock":
        return fallback

    payload = {
        "duration": beat_analysis.duration,
        "sample_rate": beat_analysis.sample_rate,
        "bpm": beat_analysis.bpm,
        "beats": beat_analysis.beats,
        "downbeats": beat_analysis.downbeats,
        "beat_strengths": beat_analysis.beat_strengths,
    }
    try:
        raw = active_provider.complete(
            director_prompt([asset.model_dump(mode="json") for asset in images], payload, style)
        )
    except Exception:
        # Provider/network failures must never stop local video generation.
        return fallback
    validated = validate_director_plan_json(raw, fallback, [asset.id for asset in images])
    return apply_transition_policy(validated, beat_analysis.beat_strengths)


def plan_to_storyboard(plan: DirectorPlan, style: VideoStyle) -> Storyboard:
    """Compatibility adapter for the existing Render Agent contract."""
    return Storyboard(
        style=style,
        scenes=[
            ScenePlan(
                scene_id=f"{index + 1:03d}",
                asset_id=item.asset_id,
                duration_frames=item.duration_frames,
                entrance=EntrancePlan(type="fade"),
                motion=MotionPlan(type=item.motion),
                transition=item.transition,
                emotion=item.reason,
            )
            for index, item in enumerate(plan.timeline)
        ],
    )


def _project_beat_analysis(state: dict) -> BeatAnalysis:
    project = state["project"]
    return state.get("beat_analysis") or BeatAnalysis(
        duration=project.audio.duration,
        sample_rate=project.audio.sample_rate,
        bpm=project.audio.bpm,
        beats=[],
        downbeats=[],
    )


def build_storyboard(state: dict) -> Storyboard:
    project = state["project"]
    style = state.get("style", "minimal")
    return plan_to_storyboard(create_director_plan(project.images, _project_beat_analysis(state), style), style)


def director_node(state: dict) -> dict:
    project = state["project"]
    style = state.get("style", "minimal")
    plan = create_director_plan(project.images, _project_beat_analysis(state), style)
    return {"director_plan": plan, "storyboard": plan_to_storyboard(plan, style)}
