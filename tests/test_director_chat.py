from content_creator.agents.director_chat_agent import revise_storyboard
from content_creator.schemas import ScenePlan, Storyboard

def test_chat_increases_third_scene_in_mock_mode(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    board = Storyboard(scenes=[ScenePlan(scene_id=f"{index:03d}", asset_id=str(index), duration_frames=60) for index in range(1, 4)])
    revised = revise_storyboard(board, "第三张图片增加停留时间")
    assert revised.scenes[2].duration_frames == 120
