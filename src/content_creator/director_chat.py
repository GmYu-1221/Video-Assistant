"""Terminal workspace for creating, editing, previewing and rendering a project."""

from __future__ import annotations

import argparse
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory

from content_creator.agents.director_chat import format_plan, generate_plan, update_plan
from content_creator.agents.remotion_agent import create_remotion_creative_plan
from content_creator.agents.render_agent import compile_render_plan
from content_creator.services.llm.router import get_agent_provider
from content_creator.services.renderer import render_project
from content_creator.sessions import ProjectSession, create_project_session, load_project_session
from typing import Callable

ProgressCallback = Callable[[str], None]


def _render(session: ProjectSession, preview: bool, on_progress: ProgressCallback | None = None) -> Path:
    if session.current_plan is None:
        session, _ = generate_plan(session, on_progress=on_progress)
    assert session.current_storyboard is not None
    creative_plan = create_remotion_creative_plan(session.current_plan, on_progress=on_progress)
    session.project = compile_render_plan(session.project, session.current_storyboard, creative_plan)
    repo_root = Path(__file__).resolve().parents[2]
    target = Path(session.preview_path if preview else session.final_video_path).resolve()
    result = render_project(session.project, repo_root / "remotion", target, preview=preview, on_progress=on_progress)
    if preview:
        session.preview_path = str(result)
    else:
        session.final_video_path = str(result)
    session.dirty = False
    session.save()
    return result


def _header(session: ProjectSession) -> None:
    print("========================================")
    print("Video Assistant Director Workspace")
    print(f"\nModel:\n{get_agent_provider('chat').model_name}")
    print(f"\nImages:\n{len(session.project.images)}")
    print(f"\nAudio:\n{session.audio_path}")
    print(f"\nCanvas:\n{session.width}x{session.height} @ {session.fps} FPS")
    print(f"\nStyle:\n{session.style}")
    print("\nCommands:\nplan\nshow [json]\npreview\nrender\nsave\nhelp\nquit")
    print("========================================")


def _help() -> None:
    print("plan: 生成或重新生成 DirectorPlan\nshow: 查看当前方案；show json 输出 JSON\npreview: 用当前方案低分辨率预览渲染\nrender: 按原始尺寸渲染 final.mp4\nsave: 保存 session.json 和 director_plan.json\nquit: 保存并退出")


def _cli_progress(message: str) -> None:
    stage, action = message.split("|", 1)
    print(f"\n{stage}\n{action}", flush=True)


def history_path(session: ProjectSession) -> Path:
    """Return the per-project prompt history file."""
    path = Path(session.project_dir).resolve() / ".director_history"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def create_prompt_session(session: ProjectSession) -> PromptSession:
    """Create a UTF-8 aware prompt with persistent history."""
    return PromptSession(history=FileHistory(str(history_path(session))))


def dispatch_command(session: ProjectSession, text: str) -> tuple[ProjectSession, bool]:
    """Handle one command; return the possibly updated session and continue flag."""
    text = text.strip()
    if text in {"quit", "exit"}:
        session.save()
        return session, False
    if text == "help":
        _help()
    elif text == "plan":
        session, response = generate_plan(session, on_progress=_cli_progress)
        session.save(); print(response)
    elif text in {"show", "show json"}:
        print(format_plan(session, as_json=text == "show json"))
    elif text == "save":
        session.save(); print("当前计划已保存。")
    elif text == "preview":
        result = _render(session, preview=True, on_progress=_cli_progress)
        print(f"\n✅ 完成\n预览路径：{result}")
    elif text == "render":
        result = _render(session, preview=False, on_progress=_cli_progress)
        print(f"\n✅ 完成\n渲染路径：{result}")
    elif text:
        _cli_progress("导演助手|正在理解创意需求...")
        try:
            session, response = update_plan(session, text, on_progress=_cli_progress)
        except TypeError as exc:
            # Preserve compatibility with integrations that monkeypatch the
            # historical two-argument command helper.
            if "on_progress" not in str(exc):
                raise
            session, response = update_plan(session, text)
        session.save()
        print(f"\n✅ 完成\n{response}\n当前计划已保存。输入 show 查看完整方案，输入 preview 生成预览。")
    return session, True


def _parse_session(args: argparse.Namespace) -> ProjectSession:
    if args.project:
        return load_project_session(args.project)
    return create_project_session(args.images, args.audio, args.output, args.width, args.height, args.fps, args.style)


def main() -> int:
    parser = argparse.ArgumentParser(description="Video Assistant Director Workspace")
    parser.add_argument("--project", type=Path)
    parser.add_argument("--images")
    parser.add_argument("--audio")
    parser.add_argument("--output", default="./output")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--style", default="cinematic")
    args = parser.parse_args()
    if args.project and (args.images or args.audio):
        parser.error("Use either --project or --images with --audio, not both")
    if not args.project and (not args.images or not args.audio):
        parser.error("New workspace requires --images and --audio")
    session = _parse_session(args)
    _header(session)
    prompt_session = create_prompt_session(session)
    while True:
        try:
            text = prompt_session.prompt("\nDirector> ").strip()
        except (EOFError, KeyboardInterrupt):
            text = "quit"
        session, keep_running = dispatch_command(session, text)
        if not keep_running:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
