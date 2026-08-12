import json
from pathlib import Path
from content_creator.schemas import AnimationPlan, DirectorPlan, DirectorTimelineItem, TimelineItem, TransitionEffectPlan, VideoProject
from content_creator.agents.remotion_agent import create_remotion_plans
from content_creator.services.music import adapt_audio_to_duration

def compile_render_plan(project: VideoProject, storyboard, animation_plan: AnimationPlan | None = None, transition_effect_plan: TransitionEffectPlan | None = None) -> VideoProject:
    cursor = 0
    timeline = []
    if animation_plan is None or transition_effect_plan is None:
        # Storyboard is a durable plan boundary. Rebuild a compatible DirectorPlan
        # so animations survive callers that compile a storyboard directly.
        rebuilt_plan = DirectorPlan(timeline=[DirectorTimelineItem(asset_id=scene.asset_id, duration_frames=scene.duration_frames, transition=scene.transition, motion=scene.motion.type, reason=scene.emotion, creative_intent=scene.creative_intent, transition_intent=scene.transition_intent, timing=scene.timing) for scene in storyboard.scenes])
        generated_animation, generated_transitions = create_remotion_plans(rebuilt_plan)
        animation_plan = animation_plan or generated_animation
        transition_effect_plan = transition_effect_plan or generated_transitions
    animation_by_asset = {item.asset_id: item for item in animation_plan.animations}
    transition_by_source = {item.from_asset_id: item for item in transition_effect_plan.transitions}
    for scene in storyboard.scenes:
        end = cursor + scene.duration_frames
        timeline.append(TimelineItem(asset_id=scene.asset_id, start_frame=cursor, end_frame=end, duration_frames=scene.duration_frames, transition=scene.transition, animation=animation_by_asset.get(scene.asset_id), transition_effect=transition_by_source.get(scene.asset_id)))
        cursor = end
    project_dir = Path(project.output.project_dir).resolve()
    audio_dir = project_dir / "audio"
    if not audio_dir.is_dir():
        raise RuntimeError(f"Project audio directory does not exist: {audio_dir}")
    audio_path = audio_dir / "bgm_adapted.wav"
    source_relative = project.audio.source_path
    if not source_relative:
        raise RuntimeError("Project audio source_path is missing; cannot adapt BGM safely")
    source_audio = (project_dir / source_relative).resolve()
    if not source_audio.is_file() or source_audio.parent != audio_dir:
        raise RuntimeError(f"Project source audio does not exist inside audio directory: {source_audio}")
    adapt_audio_to_duration(source_audio, cursor / project.fps, audio_path)
    updated = project.model_copy(update={"timeline": timeline, "audio": project.audio.model_copy(update={"path":"audio/bgm_adapted.wav", "duration": cursor / project.fps, "sample_rate":44100})})
    payload = updated.model_dump(mode="json")
    payload["output"] = {"project_dir":".", "render_data":"render_data.json", "final_video":"render/final.mp4"}
    Path(updated.output.render_data).resolve().write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return updated

def render_node(state: dict) -> dict:
    project = compile_render_plan(state["project"], state["storyboard"], state.get("animation_plan"), state.get("transition_effect_plan"))
    return {"project": project, "render_plan": project.model_dump(mode="json")}
