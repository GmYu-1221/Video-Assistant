import json
from pathlib import Path

from content_creator.agents.director_agent import plan_to_storyboard
from content_creator.agents.remotion_agent import create_remotion_plans
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
    registry = Path("remotion/src/transitions/index.tsx").read_text(encoding="utf-8")
    presentation = Path("remotion/src/transitions/presentations/glass-shatter.tsx").read_text(encoding="utf-8")
    assert "item.transition_effect" in composition
    assert "TransitionEffectFactory" in composition
    assert "TransitionEffectRegistry" in registry
    assert "glass_shatter_transition" in registry
    assert "clipPath" in presentation
    assert "opacity" in presentation
    assert "rotate" in presentation
