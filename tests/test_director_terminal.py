from pathlib import Path
from types import SimpleNamespace

from content_creator import director_chat
from content_creator.director_chat import _render, create_prompt_session, dispatch_command, history_path
from content_creator.sessions.project_session import ProjectSession
from content_creator.schemas import VideoCopy


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


def test_director_render_uses_quiet_remotion_output(tmp_path, monkeypatch):
    target = tmp_path / "preview.mp4"
    session = SimpleNamespace(
        current_plan=object(),
        current_storyboard=object(),
        project=object(),
        preview_path=str(target),
        final_video_path=str(tmp_path / "final.mp4"),
        dirty=True,
        save=lambda: None,
    )
    captured = {}
    monkeypatch.setattr(director_chat, "create_remotion_creative_plan", lambda *args, **kwargs: object())
    monkeypatch.setattr(director_chat, "create_visual_spec_decision", lambda *args, **kwargs: object())
    monkeypatch.setattr(director_chat, "compile_render_plan", lambda project, *args, **kwargs: project)

    def fake_render(*args, **kwargs):
        captured.update(kwargs)
        return target

    monkeypatch.setattr(director_chat, "render_project", fake_render)
    assert _render(session, preview=True) == target
    assert captured["quiet"] is True


def test_copy_commands_persist_and_clear(tmp_path, monkeypatch):
    session = _session(tmp_path)
    session.project = SimpleNamespace(video_copy=VideoCopy())
    saved = []
    monkeypatch.setattr(ProjectSession, "save", lambda self: saved.append(True))
    dispatch_command(session, "设置标题：新模型发布")
    dispatch_command(session, "设置副标题: 参数与能力")
    dispatch_command(session, "设置正文：这里是正文")
    assert session.project.video_copy.model_dump() == {"headline": "新模型发布", "subtitle": "参数与能力", "body": "这里是正文"}
    dispatch_command(session, "清空文案")
    assert session.project.video_copy.model_dump() == {"headline": "", "subtitle": "", "body": ""}
    assert len(saved) == 4
