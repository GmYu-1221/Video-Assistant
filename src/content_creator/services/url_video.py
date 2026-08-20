"""Application service for the one production URL-to-video pipeline."""
from __future__ import annotations

import json
from pathlib import Path

from content_creator.config import PROJECT_ROOT
from content_creator.schemas import AnimationArtifact, ProjectContext
from content_creator.services.artifact_validation import validate_final_artifact
from content_creator.services.music import adapt_audio_to_duration, load_catalog, select_track
from content_creator.services.renderer import ChromiumRenderer
from content_creator.services.runtime import prepare_project_runtime
from content_creator.workflow import build_graph


_NODE_STAGES = {
    "source_agent": "文章处理",
    "editorial_agent": "内容编排",
    "director_agent": "导演设计",
    "copy_fitting_agent": "文案适配",
    "presentation_compiler": "分页编译",
    "director_review": "导演复核",
    "animation_agent": "动画生成",
}


def create_project_context(project_id: str, urls: list[str], output_root: str | Path) -> ProjectContext:
    project_dir = Path(output_root).resolve() / "projects" / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    for directory in ("materials", "audio", "render", "sources"):
        (project_dir / directory).mkdir(exist_ok=True)
    prepare_project_runtime(project_dir)
    context = ProjectContext(project_id=project_id, project_dir=str(project_dir), urls=urls)
    _write_json(project_dir / "project.json", context.model_dump(mode="json"))
    return context


def generate_animation(context: ProjectContext, *, on_progress=None) -> tuple[AnimationArtifact, dict]:
    state: dict = {"project": context, "revision_count": 0, "scene_split_count": 0, "errors": []}
    graph = build_graph()
    for update in graph.stream(state, stream_mode="updates"):
        for node, values in update.items():
            state.update(values or {})
            if on_progress and node in _NODE_STAGES:
                on_progress(_NODE_STAGES[node])
    artifact = state.get("animation_artifact")
    if not isinstance(artifact, AnimationArtifact):
        raise RuntimeError("Animation graph ended without an AnimationArtifact")
    return artifact, state


def render_animation(artifact: AnimationArtifact, state: dict, *, on_progress=None) -> Path:
    project_dir = Path(state["project"].project_dir)
    editorial = state["editorial_plan"]
    tracks = load_catalog(PROJECT_ROOT)
    track = select_track(tracks, editorial.mood, editorial.topics)
    duration = artifact.duration_frames / artifact.fps
    bgm_path = adapt_audio_to_duration(track.path, duration, project_dir / "audio" / "bgm_adapted.wav")
    _write_json(project_dir / "audio" / "selection.json", {
        "track_id": track.id, "source_path": track.path, "license_note": track.license_note,
        "duration_seconds": duration,
    })
    output = project_dir / "render" / "final.mp4"
    renderer = ChromiumRenderer()
    renderer.render(
        artifact, project_dir, bgm_path, output,
        on_progress=(lambda current, total: on_progress(f"视频渲染 {current}/{total}")) if on_progress else None,
    )
    validation = validate_final_artifact(output, width=artifact.width, height=artifact.height, fps=artifact.fps, duration_seconds=duration)
    _write_json(project_dir / "render" / "validation.json", validation)
    if not validation["passed"]:
        raise RuntimeError("最终视频校验失败：" + "；".join(validation["errors"]))
    return output


def run_url_video_project(context: ProjectContext, *, on_progress=None) -> Path:
    artifact, state = generate_animation(context, on_progress=on_progress)
    if on_progress:
        on_progress("视频渲染")
    return render_animation(artifact, state, on_progress=on_progress)


def _write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
