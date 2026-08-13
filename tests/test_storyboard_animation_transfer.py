import json
from pathlib import Path

from content_creator.agents.director_agent import plan_to_storyboard
from content_creator.agents.render_agent import compile_render_plan
from content_creator.schemas import AudioConfig, DirectorPlan, ImageAsset, TimelineItem, TransitionConfig, VideoOutput, VideoProject


class ParticleLLM:
    model_name = "remotion-test"

    def complete_json(self, _prompt: str) -> str:
        return '{"type":"particle_flip_reveal","duration_frames":24,"params":{"particle_density":120,"rotation_axis":"Y"}}'


def test_creative_intent_survives_storyboard_and_render_data(tmp_path, monkeypatch):
    monkeypatch.setattr("content_creator.agents.remotion_agent.get_agent_provider", lambda _: ParticleLLM())
    director_plan = DirectorPlan.model_validate({"timeline": [{"asset_id": "image-001", "duration_frames": 60, "reason": "opening", "creative_intent": {"description": "Image forms from particles and rotates into view", "movement": "Y rotation", "effects": ["particle dissolve"]}}]})
    storyboard = plan_to_storyboard(director_plan, "cinematic")
    scene = storyboard.scenes[0]
    assert scene.creative_intent is not None
    assert "particles" in scene.creative_intent.description
    assert scene.entrance.type == "none"

    root = tmp_path / "project"; audio_dir = root / "audio"; audio_dir.mkdir(parents=True)
    (audio_dir / "source.wav").write_bytes(b"audio")
    project = VideoProject(project_id="p", images=[ImageAsset(id="image-001", filename="a.jpg", relative_path="a.jpg", width=100, height=100)], audio=AudioConfig(path="audio/bgm_adapted.wav", source_path="audio/source.wav", duration=1, sample_rate=44100), timeline=[TimelineItem(asset_id="image-001", start_frame=0, end_frame=1, duration_frames=1, transition=TransitionConfig())], output=VideoOutput(project_dir=str(root), render_data=str(root / "render_data.json"), final_video=str(root / "final.mp4")))
    monkeypatch.setattr("content_creator.agents.render_agent.adapt_audio_to_duration", lambda *_args: None)
    result = compile_render_plan(project, storyboard)
    payload = json.loads(Path(result.output.render_data).read_text(encoding="utf-8"))
    assert payload["timeline"][0]["animation"]["type"] == "particle_flip_reveal"
