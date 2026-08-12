import json
from pathlib import Path
from content_creator.schemas import AnimationPlan, TimelineItem, VideoProject
from content_creator.services.music import adapt_audio_to_duration

def compile_render_plan(project: VideoProject, storyboard, animation_plan: AnimationPlan | None = None) -> VideoProject:
    cursor = 0
    timeline = []
    animation_by_asset = {item.asset_id: item for item in animation_plan.animations} if animation_plan else {}
    for scene in storyboard.scenes:
        end = cursor + scene.duration_frames
        timeline.append(TimelineItem(asset_id=scene.asset_id, start_frame=cursor, end_frame=end, duration_frames=scene.duration_frames, transition=scene.transition, animation=animation_by_asset.get(scene.asset_id)))
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
    project = compile_render_plan(state["project"], state["storyboard"], state.get("animation_plan"))
    return {"project": project, "render_plan": project.model_dump(mode="json")}
