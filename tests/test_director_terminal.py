from pathlib import Path

from content_creator.director_chat import create_prompt_session, dispatch_command, history_path
from content_creator.sessions.project_session import ProjectSession


def _session(tmp_path: Path) -> ProjectSession:
    # Avoid media initialization: the prompt and command helpers only require
    # the persisted project path and the session save contract.
    return ProjectSession.model_construct(project_dir=str(tmp_path), current_plan=None)


def test_prompt_initialization_uses_project_history(tmp_path):
    session = _session(tmp_path)
    prompt = create_prompt_session(session)
    assert prompt is not None
    assert history_path(session) == tmp_path.resolve() / ".director_history"
    assert history_path(session).parent == tmp_path.resolve()


def test_command_dispatch_quit_is_unchanged(tmp_path, monkeypatch):
    session = _session(tmp_path)
    saved = []
    monkeypatch.setattr(ProjectSession, "save", lambda self: saved.append(True))
    updated, keep_running = dispatch_command(session, "quit")
    assert updated is session
    assert keep_running is False
    assert saved == [True]


def test_unicode_text_is_passed_to_director_agent(tmp_path, monkeypatch):
    session = _session(tmp_path)
    captured = []

    def fake_update(current, message):
        captured.append(message)
        return current, "已记录"

    monkeypatch.setattr("content_creator.director_chat.update_plan", fake_update)
    monkeypatch.setattr(ProjectSession, "save", lambda self: None)
    dispatch_command(session, "第一张照片从背面翻转进入")
    assert captured == ["第一张照片从背面翻转进入"]
