import argparse, json, shutil
from datetime import datetime
from pathlib import Path
from content_creator.schemas import AudioConfig, VideoOutput, VideoProject
from content_creator.schemas.exporter import export_types
from content_creator.security.files import AUDIO_EXTENSIONS, validate_regular_file
from content_creator.services.assets import scan_and_process
from content_creator.services.music import analyze_audio
from content_creator.services.timeline import build_timeline


def create_project(args: argparse.Namespace) -> VideoProject:
    audio = validate_regular_file(args.audio, AUDIO_EXTENSIONS)
    project_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    project_dir = Path(args.output).resolve() / "projects" / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    audio_dir = project_dir / "audio"; audio_dir.mkdir()
    audio_target = audio_dir / audio.name; shutil.copy2(audio, audio_target)
    assets = scan_and_process(args.images, project_dir, (args.width, args.height))
    analysis = analyze_audio(str(audio_target))
    for asset in assets: asset.duration_frames = max(1, round(analysis.duration * args.fps / len(assets)))
    timeline = build_timeline(assets, analysis, args.fps)
    output = VideoOutput(project_dir=str(project_dir), render_data=str(project_dir / "render_data.json"), final_video=str(project_dir / "render" / "final.mp4"))
    project = VideoProject(project_id=project_id, fps=args.fps, width=args.width, height=args.height, images=assets, audio=AudioConfig(path="audio/" + audio.name, duration=analysis.duration, sample_rate=analysis.sample_rate, bpm=analysis.bpm), timeline=timeline, output=output)
    exported = project.model_dump(mode="json")
    exported["output"] = {"project_dir": ".", "render_data": "render_data.json", "final_video": "render/final.mp4"}
    Path(output.render_data).write_text(json.dumps(exported, indent=2), encoding="utf-8")
    return project


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a beat-synchronized image video locally")
    parser.add_argument("--images", required=True); parser.add_argument("--audio", required=True); parser.add_argument("--output", default="output")
    parser.add_argument("--width", type=int, default=1920); parser.add_argument("--height", type=int, default=1080); parser.add_argument("--fps", type=int, default=30); parser.add_argument("--preview", action="store_true")
    args = parser.parse_args(); project = create_project(args)
    repo_root = Path(__file__).resolve().parents[2]
    export_types(repo_root / "remotion/src/types.ts")
    from content_creator.services.renderer import render_project
    render_project(project, repo_root / "remotion", project.output.final_video, args.preview)
    print(project.output.final_video)


if __name__ == "__main__": main()
