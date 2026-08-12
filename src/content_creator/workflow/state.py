from typing import Any, TypedDict
from content_creator.schemas import AnimationPlan, DirectorPlan, ImageAnalysis, RemotionAdvice, Storyboard, TransitionEffectPlan, VideoProject
from content_creator.services.music.beat_detector import BeatAnalysis

class VideoState(TypedDict, total=False):
    project: VideoProject
    style: str
    image_analysis: list[ImageAnalysis]
    beat_analysis: BeatAnalysis
    director_plan: DirectorPlan
    animation_plan: AnimationPlan
    transition_effect_plan: TransitionEffectPlan
    storyboard: Storyboard
    remotion_advice: RemotionAdvice
    render_plan: dict[str, Any]
    errors: list[str]
