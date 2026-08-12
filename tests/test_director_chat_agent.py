from content_creator.agents.director_chat import DirectorSession, handle_message
from content_creator.schemas import DirectorPlan


def test_legacy_director_session_is_explicitly_non_mutating():
    session = DirectorSession(images=[{"id": "a"}], beat_analysis=None, current_plan=DirectorPlan.model_validate({"timeline": [{"asset_id": "a", "duration_frames": 60, "reason": "opening"}]}))
    updated, response = handle_message(session, "第一张图片从背后翻转进入")
    assert updated.current_plan.timeline[0].creative_intent is None
    assert "ProjectSession" in response
    assert len(updated.conversation_history) == 2
