from content_creator.agents.remotion_agent import create_animation_plan
from content_creator.schemas import DirectorPlan


class ParticleLLM:
    model_name = "remotion-test"

    def complete_json(self, _prompt: str) -> str:
        return '{"type":"particle_flip_reveal","duration_frames":24,"params":{"particle_density":120,"rotation_axis":"Y"}}'


def test_particle_flip_design_is_not_forced_into_legacy_animation_type(monkeypatch):
    monkeypatch.setattr("content_creator.agents.remotion_agent.get_agent_provider", lambda _: ParticleLLM())
    plan = DirectorPlan.model_validate({"timeline": [{
        "asset_id": "image-001",
        "duration_frames": 60,
        "reason": "creative opening",
        "creative_intent": {
            "description": "Image forms from particles and rotates into view",
            "movement": "3D rotation",
            "effects": ["particle dissolve", "motion blur"],
            "energy": 0.9,
        },
    }]})

    item = plan.timeline[0]
    animation = create_animation_plan(plan, mode="creative").animations[0]

    assert "particle dissolve" in item.creative_intent.effects
    assert animation.effect.value == "particle_flip_reveal"
    assert animation.component == "ParticleFlipReveal"
    assert animation.effect.value != "none"
