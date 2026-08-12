from typing import Any, TypedDict
from content_creator.schemas import ImageAnalysis, RemotionAdvice, Storyboard, VideoProject

class VideoState(TypedDict, total=False):
    project: VideoProject
    style: str
    image_analysis: list[ImageAnalysis]
    storyboard: Storyboard
    remotion_advice: RemotionAdvice
    render_plan: dict[str, Any]
    errors: list[str]
