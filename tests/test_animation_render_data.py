from pathlib import Path

from content_creator.agents.render_agent import compile_render_plan
from content_creator.schemas import AnimationEffect, AnimationEffectType, AudioConfig, ImageAsset, ScenePlan, Storyboard, TimelineItem, TransitionConfig, VideoOutput, VideoProject


def test_render_data_contains_animation(tmp_path, monkeypatch):
    root = tmp_path / "project"; audio = root / "audio"; audio.mkdir(parents=True)
    source = audio / "source.wav"; source.write_bytes(b"audio")
    project = VideoProject(project_id="p", images=[ImageAsset(id="a", filename="a.jpg", relative_path="materials/processed/a.jpg", width=100, height=100)], audio=AudioConfig(path="audio/bgm_adapted.wav", source_path="audio/source.wav", duration=1, sample_rate=44100), timeline=[TimelineItem(asset_id="a", start_frame=0, end_frame=1, duration_frames=1, transition=TransitionConfig())], output=VideoOutput(project_dir=str(root), render_data=str(root / "render_data.json"), final_video=str(root / "render/final.mp4")))
    monkeypatch.setattr("content_creator.agents.render_agent.adapt_audio_to_duration", lambda *_args: audio / "bgm_adapted.wav")
    animation = AnimationEffect(asset_id="a", type=AnimationEffectType.card_flip_reveal, component="CardFlipReveal", implementation="custom", duration_frames=18, params={}, fallback=AnimationEffectType.none)
    updated = compile_render_plan(project, Storyboard(scenes=[ScenePlan(scene_id="001", asset_id="a", duration_frames=60)]), type("Plan", (), {"animations": [animation]})())
    assert updated.timeline[0].animation == animation
    assert '"card_flip_reveal"' in Path(updated.output.render_data).read_text()
