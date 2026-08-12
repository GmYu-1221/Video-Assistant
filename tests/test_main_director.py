import json
from argparse import Namespace

from content_creator.main import apply_director
from content_creator.agents.director_agent import create_director_plan as generate_plan
from content_creator.schemas import AudioConfig, ImageAsset, RGBColor, TimelineItem, TransitionConfig, VideoOutput, VideoProject
from content_creator.services.music.beat_detector import BeatAnalysis


def test_director_plan_is_saved_and_converted_to_timeline(tmp_path, monkeypatch):
    project_dir = tmp_path / "project"
    audio_dir = project_dir / "audio"
    audio_dir.mkdir(parents=True)
    (audio_dir / "source.wav").write_bytes(b"not audio")
    project = VideoProject(
        project_id="p1",
        images=[ImageAsset(id="a", filename="a.jpg", relative_path="materials/a.jpg", width=100, height=100)],
        audio=AudioConfig(path="audio/source.wav", duration=1, sample_rate=44100),
        timeline=[TimelineItem(asset_id="a", start_frame=0, end_frame=30, duration_frames=30, transition=TransitionConfig())],
        output=VideoOutput(project_dir=str(project_dir), render_data=str(project_dir / "render_data.json"), final_video=str(project_dir / "render/final.mp4")),
    )
    analysis = BeatAnalysis(duration=1, sample_rate=44100, bpm=120, beats=[], downbeats=[])
    monkeypatch.setattr(
        "content_creator.main.create_director_plan",
        lambda images, beat_analysis, style: generate_plan(images, beat_analysis, style),
    )
    monkeypatch.setattr("content_creator.main.compile_render_plan", lambda current, storyboard: current)

    updated = apply_director(project, analysis, "minimal")
    plan = json.loads((project_dir / "director_plan.json").read_text())

    assert len(plan["timeline"]) == 1
    assert updated.timeline[0].asset_id == "a"
