import argparse, json, shutil
from datetime import datetime
from pathlib import Path
from content_creator.schemas import AudioConfig, VideoOutput, VideoProject, TransitionPolicy, PRESETS
from content_creator.schemas.exporter import export_types
from content_creator.security.files import AUDIO_EXTENSIONS, validate_regular_file
from content_creator.services.assets import scan_and_process
from content_creator.services.music import analyze_audio, adapt_audio_to_duration
from content_creator.services.music.beat_detector import BeatAnalysis
from content_creator.services.timeline import build_timeline
from content_creator.agents.director_agent import create_director_plan, plan_to_storyboard
from content_creator.agents.render_agent import compile_render_plan
from content_creator.agents.remotion_agent import create_remotion_plans
from content_creator.services.llm.router import get_agent_provider


def _create_project(args: argparse.Namespace) -> tuple[VideoProject, BeatAnalysis]:
    audio = validate_regular_file(args.audio, AUDIO_EXTENSIONS)
    project_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    project_dir = Path(args.output).resolve() / "projects" / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    audio_dir = project_dir / "audio"; audio_dir.mkdir(parents=True, exist_ok=True)
    audio_target = audio_dir / audio.name; shutil.copy2(audio, audio_target)
    assets = scan_and_process(args.images, project_dir, (args.width, args.height))
    analysis = analyze_audio(str(audio_target))
    allowed = PRESETS.get(args.style, PRESETS["minimal"])
    policy = TransitionPolicy(mode=args.transition_mode, allowed=allowed, seed=0)
    timeline = build_timeline(assets, analysis, args.fps, policy=policy, style=args.style)
    total_frames = max(item.end_frame for item in timeline)
    adapted_name = "bgm_adapted.wav"
    adapt_audio_to_duration(audio_target, total_frames / args.fps, audio_dir / adapted_name)
    output = VideoOutput(project_dir=str(project_dir), render_data=str(project_dir / "render_data.json"), final_video=str(project_dir / "render" / "final.mp4"))
    project = VideoProject(project_id=project_id, fps=args.fps, width=args.width, height=args.height, images=assets, audio=AudioConfig(path="audio/" + adapted_name, source_path="audio/" + audio.name, duration=total_frames / args.fps, sample_rate=analysis.sample_rate, bpm=analysis.bpm), timeline=timeline, output=output)
    exported = project.model_dump(mode="json")
    exported["output"] = {"project_dir": ".", "render_data": "render_data.json", "final_video": "render/final.mp4"}
    Path(output.render_data).write_text(json.dumps(exported, indent=2), encoding="utf-8")
    return project, analysis


def create_project(args: argparse.Namespace) -> VideoProject:
    """Build the original rule-based project; kept as a stable Python API."""
    project, _analysis = _create_project(args)
    return project


def apply_director(project: VideoProject, analysis: BeatAnalysis, style: str) -> VideoProject:
    """Run the Director and adapt its validated decisions to the render pipeline."""
    print("[Director] Analyzing assets")
    print("[Director] Generating plan")
    plan = create_director_plan(project.images, analysis, style)
    plan_path = Path(project.output.project_dir) / "director_plan.json"
    plan_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    print("[Director] Plan validated")
    storyboard = plan_to_storyboard(plan, style)
    animation_plan, transition_effect_plan = create_remotion_plans(plan)
    try:
        return compile_render_plan(project, storyboard, animation_plan, transition_effect_plan)
    except TypeError as exc:
        # Keep compatibility with callers/tests that inject the legacy 2-arg compiler.
        if "positional argument" not in str(exc):
            raise
        return compile_render_plan(project, storyboard)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a beat-synchronized image video locally")
    parser.add_argument("--images", required=True); parser.add_argument("--audio", required=True); parser.add_argument("--output", default="output")
    parser.add_argument("--width", type=int, default=1920); parser.add_argument("--height", type=int, default=1080); parser.add_argument("--fps", type=int, default=30); parser.add_argument("--preview", action="store_true")
    parser.add_argument("--transition-mode", choices=["random", "sequential", "weighted"], default="sequential")
    parser.add_argument("--style", choices=sorted(PRESETS), default="minimal")
    parser.add_argument("--agent-mode", action="store_true")
    parser.add_argument(
        "--director",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Use the Director Agent when a configured LLM is available (default: auto)",
    )
    args = parser.parse_args(); project, analysis = _create_project(args)
    director_provider = get_agent_provider("director")
    director_enabled = args.director if args.director is not None else director_provider.model_name != "mock"
    if director_enabled:
        try:
            project = apply_director(project, analysis, args.style)
        except Exception as exc:
            print(f"[Director] Failed, using rule-based storyboard: {type(exc).__name__}: {exc}")
    if args.agent_mode:
        print(f"Content Creator\nLLM: {director_provider.model_name}\nAgents: Director={director_provider.model_name}, Remotion={get_agent_provider('remotion').model_name}, Renderer=local")
        from content_creator.workflow import build_graph
        result = build_graph().invoke({"project": project, "style": args.style, "errors": []})
        project = result["project"]
    repo_root = Path(__file__).resolve().parents[2]
    export_types(repo_root / "remotion/src/types.ts")
    from content_creator.services.renderer import render_project
    render_project(project, repo_root / "remotion", project.output.final_video, args.preview)
    print(project.output.final_video)


if __name__ == "__main__": main()
