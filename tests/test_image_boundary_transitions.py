import json

from content_creator.agents.render_agent import compile_render_plan
from content_creator.schemas import (
    AudioConfig, ImageAsset, RemotionCreativePlan, ScenePlan, Storyboard,
    TimelineItem, TransitionConfig, VideoOutput, VideoProject,
)


def test_every_outgoing_image_boundary_gets_registered_transition(tmp_path, monkeypatch):
    root = tmp_path / "project"
    audio = root / "audio"
    audio.mkdir(parents=True)
    (audio / "source.wav").write_bytes(b"audio")
    images = [ImageAsset(id=f"image-{index}", filename=f"{index}.jpg", relative_path=f"{index}.jpg", width=1280, height=720) for index in range(3)]
    timeline = [TimelineItem(asset_id=image.id, start_frame=index * 60, end_frame=(index + 1) * 60, duration_frames=60, transition=TransitionConfig()) for index, image in enumerate(images)]
    project = VideoProject(
        project_id="boundary-test", images=images,
        audio=AudioConfig(path="audio/source.wav", source_path="audio/source.wav", duration=6, sample_rate=44100),
        timeline=timeline,
        output=VideoOutput(project_dir=str(root), render_data=str(root / "render_data.json"), final_video=str(root / "final.mp4")),
    )
    storyboard = Storyboard(scenes=[ScenePlan(scene_id=f"scene-{index}", asset_id=image.id, duration_frames=60, transition=TransitionConfig()) for index, image in enumerate(images)])
    monkeypatch.setattr("content_creator.agents.render_agent.adapt_audio_to_duration", lambda *_args: None)

    rendered = compile_render_plan(project, storyboard, creative_plan=RemotionCreativePlan(plans=[]))

    assert [item.transition_effect is not None for item in rendered.timeline] == [True, True, False]
    assert [(item.transition_effect.from_asset_id, item.transition_effect.to_asset_id) for item in rendered.timeline[:-1]] == [
        ("image-0", "image-1"), ("image-1", "image-2"),
    ]
    assert all(item.transition_effect.params["template_id"] == "qwen3_8" for item in rendered.timeline[:-1])
    payload = json.loads((root / "render_data.json").read_text(encoding="utf-8"))
    assert [item["transition_effect"] is not None for item in payload["timeline"]] == [True, True, False]
