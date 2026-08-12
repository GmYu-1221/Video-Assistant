from content_creator.schemas import EntrancePlan, MotionPlan, ScenePlan, Storyboard, TransitionConfig
from content_creator.services.timeline.slideshow_builder import ImageDurationPolicy

def build_storyboard(state: dict) -> Storyboard:
    project = state["project"]
    style = state.get("style", "minimal")
    policy = ImageDurationPolicy()
    beat_seconds = 60.0 / max(project.audio.bpm, 1.0)
    scenes = []
    for index, asset in enumerate(project.images):
        frames = max(1, round(policy.default_beats * beat_seconds * project.fps))
        transition = project.timeline[index].transition if index < len(project.timeline) else TransitionConfig()
        scenes.append(ScenePlan(scene_id=f"{index + 1:03d}", asset_id=asset.id, duration_frames=frames, entrance=EntrancePlan(type="fade"), motion=MotionPlan(type="static"), transition=transition, emotion="neutral"))
    return Storyboard(style=style, scenes=scenes)

def director_node(state: dict) -> dict:
    storyboard = build_storyboard(state)
    return {"storyboard": storyboard}
