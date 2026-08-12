import json
from pathlib import Path
from content_creator.schemas import TimelineItem, VideoProject
from content_creator.services.music import adapt_audio_to_duration

def compile_render_plan(project: VideoProject, storyboard) -> VideoProject:
    cursor = 0
    timeline = []
    for scene in storyboard.scenes:
        end = cursor + scene.duration_frames
        timeline.append(TimelineItem(asset_id=scene.asset_id, start_frame=cursor, end_frame=end, duration_frames=scene.duration_frames, transition=scene.transition))
        cursor = end
    audio_dir = Path(project.output.project_dir) / "audio"
    audio_path = audio_dir / "bgm_adapted.wav"
    originals = [path for path in audio_dir.iterdir() if path.is_file() and path.name != audio_path.name]
    if originals:
        adapt_audio_to_duration(originals[0], cursor / project.fps, audio_path)
    updated = project.model_copy(update={"timeline": timeline, "audio": project.audio.model_copy(update={"path":"audio/bgm_adapted.wav", "duration": cursor / project.fps, "sample_rate":44100})})
    payload = updated.model_dump(mode="json")
    payload["output"] = {"project_dir":".", "render_data":"render_data.json", "final_video":"render/final.mp4"}
    Path(project.output.render_data).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return updated

def render_node(state: dict) -> dict:
    project = compile_render_plan(state["project"], state["storyboard"])
    return {"project": project, "render_plan": project.model_dump(mode="json")}
