import json
from pathlib import Path

import pytest

from content_creator.agents.director_agent import plan_to_storyboard
from content_creator.agents.remotion_agent import create_remotion_plans, create_transition_effect_plan
from content_creator.agents.render_agent import compile_render_plan
from content_creator.schemas import AudioConfig, DirectorPlan, ImageAsset, TimelineItem, TransitionConfig, VideoOutput, VideoProject


class VisualLLM:
    model_name = "claude-remotion"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete_json(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if "transition_effect_capabilities" in prompt:
            return json.dumps({
                "type": "glass_shatter_transition", "duration_frames": 18,
                "params": {"fragment_count": 48, "impact_origin": "center", "motion_blur": True},
            })
        return json.dumps({
            "type": "particle_flip_reveal", "duration_frames": 24,
            "params": {"particle_density": 240, "rotation_axis": "Y"},
        })


class RawTransitionLLM:
    model_name = "claude-remotion"

    def __init__(self, response: str) -> None:
        self.response = response

    def complete_json(self, _prompt: str) -> str:
        return self.response


def test_one_remotion_agent_creates_animation_and_transition_render_data(tmp_path, monkeypatch):
    provider = VisualLLM()
    monkeypatch.setattr("content_creator.agents.remotion_agent.get_agent_provider", lambda _: provider)
    plan = DirectorPlan.model_validate({"timeline": [
        {
            "asset_id": "image-001", "duration_frames": 60, "reason": "opening",
            "creative_intent": {"description": "第一张图片从下往上反转进入，并且有粒子碎裂重组效果"},
            "transition_intent": {"description": "图一转图二使用玻璃破碎效果", "effects": ["glass shatter"]},
        },
        {"asset_id": "image-002", "duration_frames": 60, "reason": "reveal"},
    ]})

    animations, transitions = create_remotion_plans(plan)

    assert len(provider.prompts) == 2
    assert any("remotion_skill_guidelines" in prompt and "creative_intent" in prompt for prompt in provider.prompts)
    assert any("transition_effect_capabilities" in prompt and "glass_shatter_transition" in prompt for prompt in provider.prompts)
    assert animations.animations[0].type.value == "particle_flip_reveal"
    assert transitions.transitions[0].type.value == "glass_shatter_transition"

    root = tmp_path / "project"
    audio_dir = root / "audio"; audio_dir.mkdir(parents=True)
    (audio_dir / "source.wav").write_bytes(b"audio")
    project = VideoProject(
        project_id="p",
        images=[ImageAsset(id="image-001", filename="a.jpg", relative_path="a.jpg", width=100, height=100), ImageAsset(id="image-002", filename="b.jpg", relative_path="b.jpg", width=100, height=100)],
        audio=AudioConfig(path="audio/bgm_adapted.wav", source_path="audio/source.wav", duration=1, sample_rate=44100),
        timeline=[TimelineItem(asset_id="image-001", start_frame=0, end_frame=1, duration_frames=1, transition=TransitionConfig()), TimelineItem(asset_id="image-002", start_frame=1, end_frame=2, duration_frames=1, transition=TransitionConfig())],
        output=VideoOutput(project_dir=str(root), render_data=str(root / "render_data.json"), final_video=str(root / "final.mp4")),
    )
    monkeypatch.setattr("content_creator.agents.render_agent.adapt_audio_to_duration", lambda *_args: None)
    compile_render_plan(project, plan_to_storyboard(plan, "cinematic"), animations, transitions)
    payload = json.loads((root / "render_data.json").read_text(encoding="utf-8"))
    assert payload["timeline"][0]["animation"]["type"] == "particle_flip_reveal"
    assert payload["timeline"][0]["transition_effect"]["type"] == "glass_shatter_transition"


def test_composition_uses_independent_transition_effect_registry():
    composition = Path("remotion/src/Composition.tsx").read_text(encoding="utf-8")
    registry = Path("remotion/src/transitions/TransitionEffectRenderer.tsx").read_text(encoding="utf-8")
    presentation = Path("remotion/src/transitions/presentations/glass-shatter.tsx").read_text(encoding="utf-8")
    assert "item.transition_effect" in composition
    assert "TransitionEffectRenderer" in composition
    assert "TransitionEffectRegistry" in registry
    assert "glass_shatter_transition" in registry
    assert "clipPath" in presentation
    assert "opacity" in presentation
    assert "rotate" in presentation


def test_blur_transition_registry_contains_all_concrete_effects():
    registry = Path("remotion/src/transitions/TransitionEffectRenderer.tsx").read_text(encoding="utf-8")
    presentation = Path("remotion/src/transitions/blur/BlurTransition.tsx").read_text(encoding="utf-8")
    for effect in ["gaussian_blur_transition", "directional_blur_transition", "pixel_blur_transition", "bokeh_blur_transition", "water_ripple_transition"]:
        assert effect in registry
    assert "useVideoConfig" in presentation
    assert "spring(" in presentation
    assert "opacity: 0.2" not in presentation


@pytest.mark.parametrize("response", [
    '{"type":"glass_shatter_transition","duration_frames":45,"params":{"fragment_count":64},"description":"glass fragments"}',
    '```json\n{"type":"glass_shatter_transition","duration_frames":45,"params":{"fragment_count":64},"description":"glass fragments"}\n```',
    'Recommended cinematic transition:\n{"type":"glass_shatter_transition","duration_frames":45,"params":{"fragment_count":64},"confidence":0.92,"reason":"matches the intent"}',
])
def test_transition_effect_plan_extracts_wrapped_json_and_ignores_metadata(monkeypatch, response):
    monkeypatch.setattr("content_creator.agents.remotion_agent.get_agent_provider", lambda _: RawTransitionLLM(response))
    plan = DirectorPlan.model_validate({"timeline": [
        {"asset_id": "image-001", "duration_frames": 60, "transition_intent": {"description": "图一转图二使用玻璃破碎效果"}},
        {"asset_id": "image-002", "duration_frames": 60},
    ]})

    transitions = create_remotion_plans(plan)[1]

    assert transitions.transitions[0].type.value == "glass_shatter_transition"
    assert transitions.transitions[0].duration_frames == 45
    assert transitions.transitions[0].params == {"fragment_count": 64}


def test_transition_effect_plan_rejects_unregistered_effect(monkeypatch):
    monkeypatch.setattr(
        "content_creator.agents.remotion_agent.get_agent_provider",
        lambda _: RawTransitionLLM('{"type":"unknown_transition","duration_frames":45,"params":{}}'),
    )
    plan = DirectorPlan.model_validate({"timeline": [
        {"asset_id": "image-001", "duration_frames": 60, "transition_intent": {"description": "unknown transition"}},
        {"asset_id": "image-002", "duration_frames": 60},
    ]})
    with pytest.raises(ValueError, match="unavailable transition effect"):
        create_transition_effect_plan(plan)


def test_shake_transition_intent_generates_validated_transition_plan(monkeypatch):
    provider = RawTransitionLLM(
        '{"type":"shake_transition","duration_frames":18,"params":{"intensity":0.7,"motion_blur":true}}'
    )
    monkeypatch.setattr("content_creator.agents.remotion_agent.get_agent_provider", lambda _: provider)
    plan = DirectorPlan.model_validate({"timeline": [
        {"asset_id": "image-001", "duration_frames": 60, "transition_intent": {"description": "第二张图片抖动切出"}},
        {"asset_id": "image-002", "duration_frames": 60},
    ]})

    transition = create_transition_effect_plan(plan).transitions[0]

    assert transition.type.value == "shake_transition"
    assert transition.duration_frames == 18
    assert transition.params == {"intensity": 0.7, "motion_blur": True}


@pytest.mark.parametrize("response", [
    '{"duration_frames":18,"params":{}}',
    '{"type":"shake_transition","duration_frames":18,"params":{"intensity":"high"}}',
])
def test_invalid_transition_response_uses_safe_fallback(monkeypatch, response):
    monkeypatch.setattr("content_creator.agents.remotion_agent.get_agent_provider", lambda _: RawTransitionLLM(response))
    plan = DirectorPlan.model_validate({"timeline": [
        {"asset_id": "image-001", "duration_frames": 60, "transition_intent": {"description": "第二张图片抖动切出"}},
        {"asset_id": "image-002", "duration_frames": 60},
    ]})

    transition = create_transition_effect_plan(plan).transitions[0]

    assert transition.type.value == "shake_transition"
    assert transition.params == {"intensity": 0.45, "motion_blur": False}
    assert transition.implementation == "fallback"


def test_explicit_glass_intent_keeps_glass_fallback(monkeypatch):
    monkeypatch.setattr("content_creator.agents.remotion_agent.get_agent_provider", lambda _: RawTransitionLLM('{"duration_frames":18,"params":{}}'))
    plan = DirectorPlan.model_validate({"timeline": [
        {"asset_id": "image-001", "duration_frames": 60, "transition_intent": {"description": "玻璃破碎后切到下一张"}},
        {"asset_id": "image-002", "duration_frames": 60},
    ]})
    transition = create_transition_effect_plan(plan).transitions[0]
    assert transition.type.value == "glass_shatter_transition"
    assert transition.implementation == "fallback"


def test_unknown_strong_transition_does_not_keep_model_glass_shatter(monkeypatch):
    monkeypatch.setattr(
        "content_creator.agents.remotion_agent.get_agent_provider",
        lambda _: RawTransitionLLM('{"type":"glass_shatter_transition","duration_frames":30,"params":{"fragment_count":48}}'),
    )
    plan = DirectorPlan.model_validate({"timeline": [
        {"asset_id": "image-001", "duration_frames": 60, "transition_intent": {"description": "未知强烈转场"}},
        {"asset_id": "image-002", "duration_frames": 60},
    ]})
    transition = create_transition_effect_plan(plan).transitions[0]
    assert transition.type.value == "shake_transition"
    assert transition.params == {"intensity": 0.45, "motion_blur": False}


def test_transition_raw_response_log_is_labeled_and_redacted(monkeypatch, caplog):
    monkeypatch.setattr(
        "content_creator.agents.remotion_agent.get_agent_provider",
        lambda _: RawTransitionLLM('api_key=secret-value {"type":"glass_shatter_transition","duration_frames":45,"params":{}}'),
    )
    caplog.set_level("DEBUG")
    plan = DirectorPlan.model_validate({"timeline": [
        {"asset_id": "image-001", "duration_frames": 60, "transition_intent": {"description": "glass shatter"}},
        {"asset_id": "image-002", "duration_frames": 60},
    ]})
    create_transition_effect_plan(plan)
    messages = [record.message for record in caplog.records if "Remotion Transition RAW RESPONSE" in record.message]
    assert len(messages) == 1
    assert "secret-value" not in messages[0]
