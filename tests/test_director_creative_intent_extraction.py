import json
from pathlib import Path

from content_creator.agents.director_chat import update_plan
from content_creator.schemas import AudioConfig, DirectorPlan, ImageAsset, TimelineItem, TransitionConfig, VideoOutput, VideoProject
from content_creator.services.llm.provider import MockLLMProvider
from content_creator.sessions.project_session import BeatAnalysisSession, ProjectSession


def test_bottom_up_reverse_entrance_produces_creative_intent(tmp_path, monkeypatch):
    initial = DirectorPlan.model_validate({"timeline": [{"asset_id": "image-001", "duration_frames": 60, "reason": "opening"}]})
    project = VideoProject(project_id="p", images=[ImageAsset(id="image-001", filename="a.jpg", relative_path="a.jpg", width=100, height=100)], audio=AudioConfig(path="audio/a.wav", duration=1, sample_rate=44100), timeline=[TimelineItem(asset_id="image-001", start_frame=0, end_frame=60, duration_frames=60, transition=TransitionConfig())], output=VideoOutput(project_dir=str(tmp_path), render_data=str(tmp_path / "data.json"), final_video=str(tmp_path / "out.mp4")))
    session = ProjectSession(session_id="s", project_dir=str(tmp_path), images_dir=str(tmp_path), audio_path=str(tmp_path / "a.wav"), source_audio_path=str(tmp_path / "a.wav"), output_dir=str(tmp_path), width=1080, height=1920, fps=30, style="cinematic", project=project, beat_analysis=BeatAnalysisSession(duration=1, sample_rate=44100, bpm=120, beats=[], downbeats=[]), current_plan=initial)
    response = {"operations": [{"scene_id": "image-001", "changes": {"creative_intent": {"description": "Image enters from bottom and flips upward into view", "movement": "vertical reverse rotation", "emotion": "cinematic", "timing": "cinematic entrance", "style": "cinematic", "energy": 0.8}}}]}
    provider = MockLLMProvider(json.dumps(response)); provider.model_name = "director-test"
    monkeypatch.setattr("content_creator.agents.director_chat.get_agent_provider", lambda _: provider)

    updated, message = update_plan(session, "第一个图片从下往上反转入场")

    intent = updated.current_plan.timeline[0].creative_intent
    assert intent is not None
    assert "bottom" in intent.description
    assert "rotation" in intent.movement
    assert message == "已应用 1 个导演修改。"
