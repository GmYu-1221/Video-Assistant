from pathlib import Path

from content_creator.agents.remotion_agent import create_animation_plan
from content_creator.schemas import DirectorPlan
from content_creator.services.llm.provider import MockLLMProvider


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_descriptive_creative_intent_generates_effect_plan(monkeypatch):
    monkeypatch.setattr("content_creator.agents.remotion_agent.get_agent_provider", lambda _: MockLLMProvider())
    plan = DirectorPlan.model_validate({"timeline": [{"asset_id": "image-001", "duration_frames": 60, "reason": "test", "creative_intent": {"description": "An unknown luminous portal reveal", "movement": "vertical rise", "effects": ["glow"], "energy": 0.8}}]})
    animation = create_animation_plan(plan).animations[0]
    assert animation.implementation == "fallback"
    assert animation.type.value == "creative_reveal"
    assert animation.component == "CreativeReveal"


def test_generated_effect_is_registered_and_neutralizes_after_duration():
    registry = (REPO_ROOT / "remotion/src/effects/index.tsx").read_text(encoding="utf-8")
    effect = (REPO_ROOT / "remotion/src/effects/CreativeReveal.tsx").read_text(encoding="utf-8")
    assert "creative_reveal: CreativeReveal" in registry
    assert "if (elapsed >= duration) return <>{children}</>;" in effect
    assert "maskImage:" in effect


def test_entrance_event_is_static_after_its_lifecycle():
    renderer = (REPO_ROOT / "remotion/src/visual/VisualEffectRenderer.tsx").read_text(encoding="utf-8")
    stretch = (REPO_ROOT / "remotion/src/effects/StretchReveal.tsx").read_text(encoding="utf-8")
    assert "const endFrame = event.start_frame + event.duration_frames;" in renderer
    assert "if (frame < event.start_frame || frame >= endFrame) return <>{children}</>;" in renderer
    assert "if (event.phase === 'entrance')" in renderer
    assert "const elapsed = frame - (animation?.start_frame ?? 0);" in stretch
    assert "if (elapsed >= duration) return <>{children}</>;" in stretch


def test_camera_push_has_no_default_transparent_duplicate():
    effect = (REPO_ROOT / "remotion/src/effects/CameraPush.tsx").read_text(encoding="utf-8")
    assert "opacity: 0.2" not in effect
    assert "pointerEvents: 'none'" not in effect
    assert "{children}<div" not in effect
    assert "animation?.params.motion_blur === true" in effect
