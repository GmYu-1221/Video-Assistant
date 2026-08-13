from typing import Any, TypedDict
from content_creator.schemas import DirectorPlan, ImageAnalysis, RemotionAdvice, RemotionCreativePlan, Storyboard, VideoProject
from content_creator.services.music.beat_detector import BeatAnalysis

class VideoState(TypedDict, total=False):
    project: VideoProject
    style: str
    image_analysis: list[ImageAnalysis]
    beat_analysis: BeatAnalysis
    director_plan: DirectorPlan
    remotion_creative_plan: RemotionCreativePlan
    storyboard: Storyboard
    remotion_advice: RemotionAdvice
    render_plan: dict[str, Any]
    errors: list[str]
