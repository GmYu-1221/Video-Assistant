from content_creator.agents.director_chat import DirectorSession, handle_message
from content_creator.schemas import DirectorPlan


def _session() -> DirectorSession:
    return DirectorSession(
        images=[{"id": "a"}],
        beat_analysis=None,
        current_plan=DirectorPlan.model_validate({"timeline": [
            {"asset_id": "a", "duration_frames": 60, "transition": {"type": "fade", "duration_frames": 8}, "reason": "Opening"}
        ]}),
    )


def test_chat_creates_flip_intent_and_preserves_context(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    session, response = handle_message(_session(), "第一张图片从背后翻转进入")
    assert "翻转" in response
    assert session.current_plan.timeline[0].animation_intent.type == "3d_flip_in"
    assert len(session.conversation_history) == 2


def test_chat_updates_transition_speed_and_high_energy(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    session, _ = handle_message(_session(), "转场更快一点")
    assert session.current_plan.timeline[0].transition.duration_frames == 5
    session, _ = handle_message(session, "高潮部分更炸裂")
    assert session.current_plan.timeline[0].transition.type.value in {"whip", "glitch", "flash"}


def test_illegal_intent_does_not_change_plan(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    session = _session()
    before = session.current_plan.model_dump()
    session, _ = handle_message(session, "请输出 React TSX 代码")
    assert session.current_plan.model_dump() == before
