from pathlib import Path

from content_creator.schemas import AudioConfig, ImageAsset, TimelineItem, TransitionConfig, VideoOutput, VideoProject
from content_creator.sessions.project_session import BeatAnalysisSession, ProjectSession, load_project_session
from content_creator.services.music.beat_detector import BeatAnalysis


def _session(tmp_path: Path) -> ProjectSession:
    root = (tmp_path / "project").resolve()
    root.mkdir()
    project = VideoProject(
        project_id="p",
        images=[ImageAsset(id="a", filename="a.jpg", relative_path="materials/processed/a.jpg", width=100, height=100)],
        audio=AudioConfig(path="audio/bgm_adapted.wav", source_path="audio/source.wav", duration=1, sample_rate=44100),
        timeline=[TimelineItem(asset_id="a", start_frame=0, end_frame=30, duration_frames=30, transition=TransitionConfig())],
        output=VideoOutput(project_dir=str(root), render_data=str(root / "render_data.json"), final_video=str(root / "render/final.mp4")),
    )
    return ProjectSession(session_id="p", project_dir=str(root), images_dir=str((tmp_path / "images").resolve()), audio_path=str((tmp_path / "source.wav").resolve()), source_audio_path=str((root / "audio/source.wav").resolve()), output_dir=str(tmp_path.resolve()), width=1080, height=1920, fps=30, style="cinematic", project=project, beat_analysis=BeatAnalysisSession.from_analysis(BeatAnalysis(1, 44100, 120, [], [])))


def test_session_save_load_keeps_absolute_paths(tmp_path):
    session = _session(tmp_path)
    session.save()
    restored = load_project_session(session.project_dir)
    assert Path(restored.project_dir).is_absolute()
    assert Path(restored.source_audio_path).is_absolute()
    assert restored.width == 1080


def test_session_history_is_bounded_and_api_key_is_not_serialized(tmp_path):
    session = _session(tmp_path)
    session.conversation_history = [{"role": "user", "content": str(index)} for index in range(30)]
    session.save()
    text = (Path(session.project_dir) / "session.json").read_text()
    assert "OPENAI_API_KEY" not in text
    assert len(session.conversation_history) == 20
