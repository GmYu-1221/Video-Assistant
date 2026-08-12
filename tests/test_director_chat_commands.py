from content_creator.agents.director_chat import format_plan, update_plan
from content_creator.schemas import DirectorPlan
from content_creator.sessions.project_session import BeatAnalysisSession, ProjectSession


def test_local_chat_changes_only_requested_scene(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    plan = DirectorPlan.model_validate({"timeline": [
        {"asset_id": "a", "duration_frames": 60, "reason": "a"},
        {"asset_id": "b", "duration_frames": 90, "reason": "b"},
    ]})
    session = ProjectSession(session_id="x", project_dir=str(tmp_path), images_dir=str(tmp_path), audio_path=str(tmp_path / "a.wav"), source_audio_path=str(tmp_path / "a.wav"), output_dir=str(tmp_path), width=1920, height=1080, fps=30, style="cinematic", project=__import__("content_creator.schemas", fromlist=["VideoProject"]).VideoProject.model_construct(output=type("Output", (), {"project_dir": str(tmp_path), "render_data": str(tmp_path / "render_data.json"), "final_video": str(tmp_path / "final.mp4")})()), beat_analysis=BeatAnalysisSession(duration=1, sample_rate=44100, bpm=120, beats=[], downbeats=[]), current_plan=plan)
    updated, _ = update_plan(session, "第二张增加50%")
    assert updated.current_plan.timeline[0].duration_frames == 60
    assert updated.current_plan.timeline[1].duration_frames == 135
    assert "Scene 01" in format_plan(updated)
