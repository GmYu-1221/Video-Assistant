"""Interactive terminal Director Agent."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from content_creator.agents.director_agent import create_director_plan, plan_to_storyboard
from content_creator.agents.director_chat import DirectorSession, handle_message
from content_creator.agents.render_agent import compile_render_plan
from content_creator.schemas import DirectorPlan, VideoProject
from content_creator.services.llm.router import get_agent_provider
from content_creator.services.music.beat_detector import BeatAnalysis


def _load_session(project_dir: Path, style: str) -> DirectorSession:
    data = json.loads((project_dir / "render_data.json").read_text(encoding="utf-8"))
    project = VideoProject.model_validate(data)
    plan_path = project_dir / "director_plan.json"
    if plan_path.is_file():
        plan = DirectorPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    else:
        analysis = BeatAnalysis(project.audio.duration, project.audio.sample_rate, project.audio.bpm, [], [])
        plan = create_director_plan(project.images, analysis, style)
    return DirectorSession(
        images=[asset.model_dump(mode="json") for asset in project.images],
        beat_analysis=BeatAnalysis(project.audio.duration, project.audio.sample_rate, project.audio.bpm, [], []),
        style=style,
        current_plan=plan,
    )


def _save_session(project_dir: Path, session: DirectorSession) -> None:
    if session.current_plan:
        (project_dir / "director_plan.json").write_text(session.current_plan.model_dump_json(indent=2), encoding="utf-8")
    (project_dir / "director_session.json").write_text(json.dumps({"style": session.style, "conversation_history": session.conversation_history, "intents": [item.model_dump(mode="json") for item in session.intents]}, ensure_ascii=False, indent=2), encoding="utf-8")


def _render_current(project_dir: Path, session: DirectorSession, preview: bool) -> Path:
    data = json.loads((project_dir / "render_data.json").read_text(encoding="utf-8"))
    project = VideoProject.model_validate(data)
    updated = compile_render_plan(project, plan_to_storyboard(session.current_plan, session.style))
    from content_creator.services.renderer import render_project
    repo_root = Path(__file__).resolve().parents[2]
    return render_project(updated, repo_root / "remotion", updated.output.final_video, preview)


def main() -> int:
    parser = argparse.ArgumentParser(description="Interactive Director Agent")
    parser.add_argument("--project", type=Path, help="Existing output/projects/<id> directory")
    parser.add_argument("--style", default="cinematic")
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    project_dir = args.project.resolve() if args.project else _latest_project(Path("output/projects"))
    if project_dir is None:
        parser.error("No project found. Generate a video first or pass --project output/projects/<id>")
    session = _load_session(project_dir, args.style)
    provider = get_agent_provider("chat")
    print("--------------------------------")
    print("Video Assistant Director Agent")
    print(f"\nModel:\n{provider.model_name}")
    print("\nCommands:\nquit       exit\ngenerate   generate video plan\nrender     render current plan")
    print("--------------------------------")
    while True:
        try:
            text = input("Director> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if text.lower() in {"quit", "exit"}:
            break
        if text.lower() == "generate":
            project_data = json.loads((project_dir / "render_data.json").read_text(encoding="utf-8"))
            project = VideoProject.model_validate(project_data)
            session.current_plan = create_director_plan(project.images, session.beat_analysis, session.style)
            _save_session(project_dir, session)
            print("DirectorPlan generated and validated.")
        elif text.lower() == "render":
            path = _render_current(project_dir, session, args.preview)
            print(f"Rendered: {path}")
        elif text:
            session, response = handle_message(session, text)
            _save_session(project_dir, session)
            print(response)
            if session.current_plan:
                print(session.current_plan.model_dump_json(indent=2))
    return 0


def _latest_project(root: Path) -> Path | None:
    if not root.is_dir():
        return None
    projects = [item for item in root.iterdir() if item.is_dir() and (item / "render_data.json").is_file()]
    return max(projects, key=lambda item: item.stat().st_mtime) if projects else None


if __name__ == "__main__":
    raise SystemExit(main())
