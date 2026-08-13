import time

from content_creator.agents.director_chat import update_plan
from content_creator.schemas import DirectorPlan, VideoProject, ImageAsset
from content_creator.sessions.project_session import ProjectSession


class DelayedProvider:
    model_name = "delayed-test"

    def complete_json(self, _prompt: str) -> str:
        time.sleep(0.05)
        return '{"operations": []}'


def test_delayed_director_call_emits_chinese_progress(monkeypatch):
    events = []
    monkeypatch.setattr("content_creator.agents.director_chat.get_agent_provider", lambda _: DelayedProvider())
    plan = DirectorPlan.model_validate({"timeline": [{"asset_id": "image-001", "duration_frames": 60, "reason": "opening"}]})
    project = VideoProject.model_construct(images=[ImageAsset.model_construct(id="image-001")])
    session = ProjectSession.model_construct(project=project, current_plan=plan, style="cinematic", beat_analysis=type("Beat", (), {"model_dump": lambda self, **_: {}})(), conversation_history=[])
    _updated, response = update_plan(session, "图片跳出来抖一下", on_progress=events.append)
    assert "未修改计划" in response
    assert events[0] == "导演助手|正在理解创意需求..."
    assert "导演计划|正在更新镜头方案..." in events
    assert all("prompt" not in event.lower() and "raw" not in event.lower() for event in events)
