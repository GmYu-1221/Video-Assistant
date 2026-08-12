import json
from pathlib import Path

import pytest

from content_creator.agents.remotion_agent import create_animation_plan
from content_creator.agents.render_agent import compile_render_plan
from content_creator.schemas import AudioConfig, DirectorPlan, ImageAsset, ScenePlan, Storyboard, TransitionConfig, VideoOutput, VideoProject


class RemotionLLM:
    model_name = "claude-remotion"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        raise AssertionError("Remotion Agent must prefer complete_json")

    def complete_json(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return json.dumps({
            "type": "particle_flip_reveal",
            "duration_frames": 24,
            "params": {
                "particle_density": 120,
                "rotation_axis": "Y",
                "motion_blur": True,
                "perspective": 800,
            },
        })


class RawResponseLLM(RemotionLLM):
    def __init__(self, response: str) -> None:
        super().__init__()
        self.response = response

    def complete_json(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


def test_remotion_llm_generates_animation_plan_and_render_data(tmp_path, monkeypatch):
    provider = RemotionLLM()
    monkeypatch.setattr("content_creator.agents.remotion_agent.get_agent_provider", lambda agent: provider)
    plan = DirectorPlan.model_validate({"timeline": [{
        "asset_id": "image-001", "duration_frames": 60, "reason": "opening",
        "creative_intent": {"description": "Image flips upward from bottom with particles", "effects": ["particle dissolve"]},
    }]})

    animation_plan = create_animation_plan(plan)

    assert len(provider.prompts) == 1
    assert "remotion_skill_guidelines" in provider.prompts[0]
    assert "particle_flip_reveal" in provider.prompts[0]
    animation = animation_plan.animations[0]
    assert animation.type.value == "particle_flip_reveal"
    assert animation.implementation == "new"

    root = tmp_path / "project"
    audio_dir = root / "audio"
    audio_dir.mkdir(parents=True)
    (audio_dir / "source.wav").write_bytes(b"audio")
    project = VideoProject(
        project_id="p",
        images=[ImageAsset(id="image-001", filename="a.jpg", relative_path="a.jpg", width=100, height=100)],
        audio=AudioConfig(path="audio/bgm_adapted.wav", source_path="audio/source.wav", duration=1, sample_rate=44100),
        timeline=[{"asset_id": "image-001", "start_frame": 0, "end_frame": 1, "duration_frames": 1, "transition": {}}],
        output=VideoOutput(project_dir=str(root), render_data=str(root / "render_data.json"), final_video=str(root / "final.mp4")),
    )
    monkeypatch.setattr("content_creator.agents.render_agent.adapt_audio_to_duration", lambda *_args: None)
    compile_render_plan(project, Storyboard(scenes=[ScenePlan(scene_id="001", asset_id="image-001", duration_frames=60, transition=TransitionConfig())]), animation_plan)
    payload = json.loads((root / "render_data.json").read_text(encoding="utf-8"))
    assert payload["timeline"][0]["animation"]["type"] == "particle_flip_reveal"


def test_invalid_llm_animation_is_rejected_instead_of_using_keyword_mapping(monkeypatch):
    class InvalidLLM(RemotionLLM):
        def complete_json(self, prompt: str) -> str:
            return '{"type": "not_registered", "duration_frames": 18, "params": {}}'

    monkeypatch.setattr("content_creator.agents.remotion_agent.get_agent_provider", lambda _: InvalidLLM())
    plan = DirectorPlan.model_validate({"timeline": [{
        "asset_id": "image-001", "duration_frames": 60, "reason": "opening",
        "creative_intent": {"description": "Image flips upward from bottom with particles"},
    }]})

    with pytest.raises(ValueError, match="unavailable effect"):
        create_animation_plan(plan)


@pytest.mark.parametrize(
    "response",
    [
        '{"type":"particle_flip_reveal","duration_frames":24,"params":{}}',
        '```json\n{"type":"particle_flip_reveal","duration_frames":24,"params":{}}\n```',
        'Recommended animation:\n{"type":"particle_flip_reveal","duration_frames":24,"params":{}}\nThis preserves the cinematic reveal.',
    ],
)
def test_remotion_agent_extracts_json_wrapped_by_markdown_or_explanation(monkeypatch, response):
    provider = RawResponseLLM(response)
    monkeypatch.setattr("content_creator.agents.remotion_agent.get_agent_provider", lambda _: provider)
    plan = DirectorPlan.model_validate({"timeline": [{
        "asset_id": "image-001", "duration_frames": 60, "reason": "opening",
        "creative_intent": {"description": "particle flip reveal"},
    }]})

    animation = create_animation_plan(plan).animations[0]

    assert len(provider.prompts) == 1
    assert animation.type.value == "particle_flip_reveal"
    assert animation.implementation == "new"


def test_invalid_json_uses_fixed_creative_reveal_fallback(monkeypatch, caplog):
    monkeypatch.setattr("content_creator.agents.remotion_agent.get_agent_provider", lambda _: RawResponseLLM("not JSON"))
    plan = DirectorPlan.model_validate({"timeline": [{
        "asset_id": "image-001", "duration_frames": 12, "reason": "opening",
        "creative_intent": {"description": "particle flip reveal"},
    }]})

    animation = create_animation_plan(plan).animations[0]

    assert animation.type.value == "creative_reveal"
    assert animation.duration_frames == 12
    assert animation.params == {}
    assert animation.implementation == "fallback"
    assert "[Remotion Agent] Invalid response, using safe fallback" in caplog.text


def test_raw_response_debug_log_is_redacted_and_truncated(monkeypatch, caplog):
    monkeypatch.setattr("content_creator.agents.remotion_agent.get_agent_provider", lambda _: RawResponseLLM("api_key=secret-value " + "x" * 1100))
    caplog.set_level("DEBUG")
    plan = DirectorPlan.model_validate({"timeline": [{
        "asset_id": "image-001", "duration_frames": 60, "reason": "opening",
        "creative_intent": {"description": "reveal"},
    }]})

    create_animation_plan(plan)

    raw_messages = [record.message for record in caplog.records if "RAW RESPONSE" in record.message]
    assert len(raw_messages) == 1
    assert "secret-value" not in raw_messages[0]
    assert len(raw_messages[0]) <= 1030
