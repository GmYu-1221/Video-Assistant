import json

from content_creator.agents.remotion_agent import create_remotion_creative_plan
from content_creator.schemas import DirectorPlan


class UnifiedLLM:
    model_name = "claude-remotion"

    def __init__(self):
        self.calls = 0

    def complete_json(self, _prompt: str) -> str:
        self.calls += 1
        return json.dumps({"plans": [{"scene_id": "image-001", "visual_events": [
            {"type": "drop_reveal_elastic", "phase": "entrance", "start_frame": 0, "duration_frames": 24, "params": {"direction": "top"}},
            {"type": "glass_shatter_transition", "phase": "transition", "start_frame": 30, "duration_frames": 30, "source_asset_id": "image-001", "target_asset_id": "image-002", "params": {"fragment_count": 72}},
        ]}]})


def test_unified_remotion_plan_uses_one_llm_call(monkeypatch):
    provider = UnifiedLLM()
    monkeypatch.setattr("content_creator.agents.remotion_agent.get_agent_provider", lambda _: provider)
    plan = DirectorPlan.model_validate({"timeline": [
        {"asset_id": "image-001", "duration_frames": 60, "reason": "first", "creative_intent": {"description": "drop from above"}, "transition_intent": {"description": "glass shatter"}},
        {"asset_id": "image-002", "duration_frames": 60, "reason": "second"},
    ]})
    result = create_remotion_creative_plan(plan)
    assert provider.calls == 1
    assert [event.type for event in result.plans[0].visual_events] == ["drop_reveal_elastic", "glass_shatter_transition"]
    transition = result.plans[0].visual_events[1]
    assert transition.source_asset_id == "image-001"
    assert transition.target_asset_id == "image-002"


class ConflictingLLM(UnifiedLLM):
    def complete_json(self, _prompt: str) -> str:
        self.calls += 1
        return json.dumps({"plans": [
            {"scene_id": "image-001", "visual_events": [{"type": "glass_shatter_transition", "phase": "transition", "start_frame": 30, "duration_frames": 30, "source_asset_id": "image-001", "target_asset_id": "image-002", "params": {"fragment_count": 64}}]},
            {"scene_id": "image-002", "visual_events": [{"type": "creative_reveal", "phase": "entrance", "start_frame": 0, "duration_frames": 18, "params": {}}]},
        ]})


def test_transition_removes_target_entrance(monkeypatch):
    provider = ConflictingLLM()
    monkeypatch.setattr("content_creator.agents.remotion_agent.get_agent_provider", lambda _: provider)
    plan = DirectorPlan.model_validate({"timeline": [
        {"asset_id": "image-001", "duration_frames": 60, "reason": "first", "transition_intent": {"description": "glass shatter into image two"}},
        {"asset_id": "image-002", "duration_frames": 60, "reason": "second", "creative_intent": {"description": "appear behind fragments"}},
    ]})
    result = create_remotion_creative_plan(plan)
    assert result.plans[0].visual_events[0].type == "glass_shatter_transition"
    assert result.plans[1].visual_events == []


class TransitionConflictLLM(UnifiedLLM):
    def complete_json(self, _prompt: str) -> str:
        self.calls += 1
        return json.dumps({"plans": [{"scene_id": "image-001", "visual_events": [
            {"type": "card_flip_transition", "phase": "transition", "start_frame": 30, "duration_frames": 30, "source_asset_id": "image-001", "target_asset_id": "image-002", "params": {"rotation_axis": "Y", "perspective": 900}},
            {"type": "camera_push", "phase": "effect", "start_frame": 0, "duration_frames": 60, "params": {"intensity": 0.3}},
            {"type": "creative_reveal", "phase": "entrance", "start_frame": 35, "duration_frames": 12, "params": {}},
        ]}]})


def test_camera_push_and_card_flip_transition_are_a_valid_combination(monkeypatch):
    provider = TransitionConflictLLM()
    monkeypatch.setattr("content_creator.agents.remotion_agent.get_agent_provider", lambda _: provider)
    plan = DirectorPlan.model_validate({"timeline": [
        {"asset_id": "image-001", "duration_frames": 60, "reason": "first", "creative_intent": {"description": "图一缓慢推进"}, "transition_intent": {"description": "flip to image two"}},
        {"asset_id": "image-002", "duration_frames": 60, "reason": "second"},
    ]})
    result = create_remotion_creative_plan(plan)
    events = result.plans[0].visual_events
    assert [event.type for event in events] == ["card_flip_transition", "camera_push"]
    assert events[1].start_frame == 0
    assert events[1].duration_frames == 60
    assert events[1].params == {"intensity": 0.3}


class ParticleConflictLLM(UnifiedLLM):
    def complete_json(self, _prompt: str) -> str:
        return json.dumps({"plans": [{"scene_id": "image-001", "visual_events": [
            {"type": "glass_shatter_transition", "phase": "transition", "start_frame": 30, "duration_frames": 30, "source_asset_id": "image-001", "target_asset_id": "image-002", "params": {"fragment_count": 64}},
            {"type": "particle_flip_reveal", "phase": "entrance", "start_frame": 35, "duration_frames": 20, "params": {"particle_density": 120, "rotation_axis": "Y"}},
        ]}]})


def test_transition_removes_overlapping_particle_reveal(monkeypatch):
    monkeypatch.setattr("content_creator.agents.remotion_agent.get_agent_provider", lambda _: ParticleConflictLLM())
    plan = DirectorPlan.model_validate({"timeline": [
        {"asset_id": "image-001", "duration_frames": 60, "reason": "first", "transition_intent": {"description": "glass shatter"}},
        {"asset_id": "image-002", "duration_frames": 60, "reason": "second"},
    ]})
    result = create_remotion_creative_plan(plan)
    assert [event.type for event in result.plans[0].visual_events] == ["glass_shatter_transition"]


class StretchEntranceLLM:
    model_name = "remotion-test"

    def complete_json(self, _prompt: str) -> str:
        return json.dumps({"plans": [{"scene_id": "image-001", "visual_events": [
            {"type": "stretch_reveal", "phase": "entrance", "start_frame": 0, "duration_frames": 18, "params": {"intensity": 0.7}},
        ]}]})


def test_silk_stretch_entrance_uses_an_18_frame_visual_event(monkeypatch):
    plan = DirectorPlan.model_validate({"timeline": [{
        "asset_id": "image-001",
        "duration_frames": 60,
        "reason": "opening",
        "creative_intent": {"description": "图片丝滑拉伸进入"},
    }]})
    result = create_remotion_creative_plan(plan, provider=StretchEntranceLLM())
    event = result.plans[0].visual_events[0]
    assert event.type == "stretch_reveal"
    assert event.phase == "entrance"
    assert event.duration_frames == 18
    assert all(candidate.type != "camera_push" for candidate in result.plans[0].visual_events)


class UnwantedCameraPushLLM:
    model_name = "remotion-test"

    def complete_json(self, _prompt: str) -> str:
        return json.dumps({"plans": [{"scene_id": "image-001", "visual_events": [
            {"type": "camera_push", "phase": "effect", "start_frame": 0, "duration_frames": 60, "params": {"intensity": 0.3}},
        ]}]})


def test_cinematic_display_does_not_keep_inferred_camera_push():
    plan = DirectorPlan.model_validate({"timeline": [{
        "asset_id": "image-001",
        "duration_frames": 60,
        "reason": "opening",
        "creative_intent": {"description": "电影感展示"},
    }]})
    result = create_remotion_creative_plan(plan, provider=UnwantedCameraPushLLM())
    assert result.plans[0].visual_events == []


class BlurTransitionLLM:
    model_name = "remotion-test"

    def __init__(self, effect_type: str) -> None:
        self.effect_type = effect_type

    def complete_json(self, _prompt: str) -> str:
        return json.dumps({"plans": [{"scene_id": "image-001", "visual_events": [{
            "type": self.effect_type,
            "phase": "transition",
            "start_frame": 30,
            "duration_frames": 30,
            "source_asset_id": "image-001",
            "target_asset_id": "image-002",
            "params": {"intensity": 0.7, "softness": 0.6, "motion_blur": False},
        }]}]})


def _blur_transition_plan(intent: str) -> DirectorPlan:
    return DirectorPlan.model_validate({"timeline": [
        {"asset_id": "image-001", "duration_frames": 60, "reason": "first", "transition_intent": {"description": intent}},
        {"asset_id": "image-002", "duration_frames": 60, "reason": "second"},
    ]})


def test_defocus_intent_keeps_gaussian_blur_transition():
    result = create_remotion_creative_plan(_blur_transition_plan("图一逐渐模糊，然后出现图二"), provider=BlurTransitionLLM("gaussian_blur_transition"))
    assert [event.type for event in result.plans[0].visual_events] == ["gaussian_blur_transition"]


def test_water_intent_keeps_water_ripple_transition():
    result = create_remotion_creative_plan(_blur_transition_plan("图一像水面波纹一样过渡到图二"), provider=BlurTransitionLLM("water_ripple_transition"))
    assert [event.type for event in result.plans[0].visual_events] == ["water_ripple_transition"]


def test_fast_horizontal_blur_intent_keeps_directional_blur_transition():
    result = create_remotion_creative_plan(_blur_transition_plan("快速横向模糊切换"), provider=BlurTransitionLLM("directional_blur_transition"))
    assert [event.type for event in result.plans[0].visual_events] == ["directional_blur_transition"]


def test_cinematic_display_does_not_keep_inferred_blur_transition():
    result = create_remotion_creative_plan(_blur_transition_plan("电影感展示图片"), provider=BlurTransitionLLM("gaussian_blur_transition"))
    assert result.plans[0].visual_events == []


def test_unknown_strong_transition_downgrades_unified_glass_shatter():
    result = create_remotion_creative_plan(
        _blur_transition_plan("未知强烈转场"),
        provider=BlurTransitionLLM("glass_shatter_transition"),
    )
    event = result.plans[0].visual_events[0]
    assert event.type == "shake_transition"
    assert event.duration_frames == 18
    assert event.params == {"intensity": 0.45, "motion_blur": False}
