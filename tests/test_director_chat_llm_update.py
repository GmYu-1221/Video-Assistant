import json
from pathlib import Path

from content_creator.agents.director_chat import _sanitize_response_for_log, update_plan
from content_creator.schemas import AudioConfig, DirectorPlan, ImageAsset, TimelineItem, TransitionConfig, VideoOutput, VideoProject
from content_creator.services.llm.provider import MockLLMProvider
from content_creator.sessions.project_session import BeatAnalysisSession, ProjectSession


def _session(tmp_path: Path) -> ProjectSession:
    plan = DirectorPlan.model_validate({"timeline": [
        {"asset_id": "a", "duration_frames": 60, "transition": {"type": "fade", "duration_frames": 8}, "reason": "opening"},
        {"asset_id": "b", "duration_frames": 90, "transition": {"type": "push", "duration_frames": 6}, "reason": "middle"},
    ]})
    project = VideoProject(
        project_id="p",
        images=[ImageAsset(id="a", filename="a.jpg", relative_path="a.jpg", width=100, height=100), ImageAsset(id="b", filename="b.jpg", relative_path="b.jpg", width=100, height=100)],
        audio=AudioConfig(path="audio/a.wav", duration=1, sample_rate=44100),
        timeline=[TimelineItem(asset_id="a", start_frame=0, end_frame=60, duration_frames=60, transition=TransitionConfig()), TimelineItem(asset_id="b", start_frame=60, end_frame=150, duration_frames=90, transition=TransitionConfig())],
        output=VideoOutput(project_dir=str(tmp_path), render_data=str(tmp_path / "render_data.json"), final_video=str(tmp_path / "final.mp4")),
    )
    return ProjectSession(session_id="s", project_dir=str(tmp_path), images_dir=str(tmp_path), audio_path=str(tmp_path / "a.wav"), source_audio_path=str(tmp_path / "a.wav"), output_dir=str(tmp_path), width=1920, height=1080, fps=30, style="cinematic", project=project, beat_analysis=BeatAnalysisSession(duration=1, sample_rate=44100, bpm=120, beats=[], downbeats=[]), current_plan=plan)


def test_llm_feedback_merges_patch_and_preserves_unmentioned_scenes(tmp_path, monkeypatch):
    session = _session(tmp_path)
    original_scene_two = session.current_plan.timeline[1].model_dump()
    response = {"operations": [{"scene_id": "a", "changes": {"creative_intent": {"description": "Image softly fades into view", "movement": "opacity reveal", "timing": "18 frames", "style": "cinematic"}}}]}
    provider = MockLLMProvider(json.dumps(response))
    provider.model_name = "director-test"
    monkeypatch.setattr("content_creator.agents.director_chat.get_agent_provider", lambda _: provider)

    updated, message = update_plan(session, "第一张图片淡入")

    assert updated.current_plan.timeline[0].creative_intent.description == "Image softly fades into view"
    assert updated.current_plan.timeline[1].model_dump() == original_scene_two
    assert message == "已应用 1 个导演修改。"
    assert (tmp_path / "director_plan.json").is_file()
    assert "Image softly fades into view" in (tmp_path / "session.json").read_text()


def test_invalid_asset_id_does_not_replace_plan_and_lists_candidates(tmp_path, monkeypatch):
    session = _session(tmp_path)
    before = session.current_plan.model_dump()
    provider = MockLLMProvider(json.dumps({"operations": [{"scene_id": "scene_001", "changes": {"duration_frames": 30}}]}))
    provider.model_name = "director-test"
    monkeypatch.setattr("content_creator.agents.director_chat.get_agent_provider", lambda _: provider)

    updated, message = update_plan(session, "make the first image faster")

    assert updated.current_plan.model_dump() == before
    assert "未应用" in message
    assert "Valid asset_ids: a, b" in message


def test_debug_response_sanitizer_redacts_credentials_and_truncates():
    value = _sanitize_response_for_log("Authorization: Bearer secret-value api_key=another-secret", limit=30)
    assert "secret-value" not in value
    assert "another-secret" not in value
    assert len(value) <= 30
