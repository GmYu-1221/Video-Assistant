import json
from pathlib import Path

from content_creator.agents.remotion_agent import create_animation_plan
from content_creator.agents.render_agent import compile_render_plan
from content_creator.schemas import AudioConfig, DirectorPlan, ImageAsset, ScenePlan, Storyboard, TransitionConfig, VideoOutput, VideoProject
from content_creator.services.llm.provider import MockLLMProvider


def test_director_creative_intent_reaches_render_data(tmp_path, monkeypatch):
    monkeypatch.setattr("content_creator.agents.remotion_agent.get_agent_provider", lambda _: MockLLMProvider())
    root = tmp_path / "project"
    audio_dir = root / "audio"
    audio_dir.mkdir(parents=True)
    (audio_dir / "source.wav").write_bytes(b"audio")
    project = VideoProject(
        project_id="p",
        images=[ImageAsset(id="image-001", filename="a.jpg", relative_path="materials/a.jpg", width=100, height=100)],
        audio=AudioConfig(path="audio/bgm_adapted.wav", source_path="audio/source.wav", duration=1, sample_rate=44100),
        timeline=[{"asset_id": "image-001", "start_frame": 0, "end_frame": 1, "duration_frames": 1, "transition": {}}],
        output=VideoOutput(project_dir=str(root), render_data=str(root / "render_data.json"), final_video=str(root / "render/final.mp4")),
    )
    plan = DirectorPlan.model_validate({"timeline": [{"asset_id": "image-001", "duration_frames": 60, "reason": "flip", "creative_intent": {"description": "Image forms from particles and rotates into view", "movement": "Y rotation", "effects": ["particle dissolve"]}}]})
    animation_plan = create_animation_plan(plan)
    monkeypatch.setattr("content_creator.agents.render_agent.adapt_audio_to_duration", lambda *_args: None)
    storyboard = Storyboard(scenes=[ScenePlan(scene_id="001", asset_id="image-001", duration_frames=60, transition=TransitionConfig())])
    updated = compile_render_plan(project, storyboard, animation_plan)
    payload = json.loads(Path(updated.output.render_data).read_text(encoding="utf-8"))
    animation = payload["timeline"][0]["animation"]
    assert animation["type"] == "particle_flip_reveal"
    assert animation["params"]["particle_density"] == 120
    assert animation["params"]["rotation_axis"] == "Y"


def test_composition_dispatches_timeline_animation_to_registry():
    source = Path("remotion/src/Composition.tsx").read_text(encoding="utf-8")
    registry = Path("remotion/src/effects/index.tsx").read_text(encoding="utf-8")
    assert "item.animation" in source
    assert "EffectRenderer animation={item.animation}" in source
    assert "card_flip_reveal: CardFlipReveal" in registry
    assert "animation.type" in registry
    assert "animation.effect" not in registry
