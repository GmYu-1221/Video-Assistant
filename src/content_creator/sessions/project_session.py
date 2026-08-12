"""Persistent, absolute-path project context for Director Workspace sessions."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from content_creator.agents.vision_agent import analyze_asset
from content_creator.schemas import AudioConfig, DirectorPlan, ImageAnalysis, Storyboard, TransitionPolicy, VideoOutput, VideoProject
from content_creator.security.files import AUDIO_EXTENSIONS, validate_regular_file
from content_creator.services.assets import scan_and_process
from content_creator.services.music import adapt_audio_to_duration, analyze_audio
from content_creator.services.music.beat_detector import BeatAnalysis
from content_creator.services.timeline import build_timeline
from content_creator.schemas import PRESETS


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BeatAnalysisSession(BaseModel):
    duration: float
    sample_rate: int
    bpm: float
    beats: list[float]
    downbeats: list[float]
    beat_strengths: list[float] | None = None

    @classmethod
    def from_analysis(cls, analysis: BeatAnalysis) -> "BeatAnalysisSession":
        return cls(**analysis.__dict__)

    def to_analysis(self) -> BeatAnalysis:
        return BeatAnalysis(**self.model_dump())


class ProjectSession(BaseModel):
    session_id: str
    project_dir: str
    images_dir: str
    audio_path: str
    source_audio_path: str
    output_dir: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: int = Field(gt=0)
    style: str
    project: VideoProject
    beat_analysis: BeatAnalysisSession
    image_analysis: list[ImageAnalysis] = Field(default_factory=list)
    current_plan: DirectorPlan | None = None
    current_storyboard: Storyboard | None = None
    conversation_history: list[dict[str, str]] = Field(default_factory=list)
    preview_path: str | None = None
    final_video_path: str | None = None
    dirty: bool = False
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)

    @property
    def session_path(self) -> Path:
        return Path(self.project_dir) / "session.json"

    def save(self) -> None:
        self.updated_at = _now()
        self.conversation_history = self.conversation_history[-20:]
        root = Path(self.project_dir).resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.project.output.project_dir = str(root)
        self.session_path.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        if self.current_plan:
            (root / "director_plan.json").write_text(self.current_plan.model_dump_json(indent=2), encoding="utf-8")


def _write_render_data(project: VideoProject) -> None:
    payload = project.model_dump(mode="json")
    payload["output"] = {"project_dir": ".", "render_data": "render_data.json", "final_video": "render/final.mp4"}
    Path(project.output.render_data).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def create_project_session(images_dir: str | Path, audio_path: str | Path, output_dir: str | Path, width: int, height: int, fps: int, style: str) -> ProjectSession:
    images_root = Path(images_dir).resolve()
    source_audio = validate_regular_file(audio_path, AUDIO_EXTENSIONS).resolve()
    output_root = Path(output_dir).resolve()
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    project_dir = output_root / "projects" / session_id
    audio_dir = project_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    copied_audio = audio_dir / source_audio.name
    shutil.copy2(source_audio, copied_audio)
    assets = scan_and_process(images_root, project_dir, (width, height))
    analysis = analyze_audio(str(copied_audio))
    timeline = build_timeline(assets, analysis, fps, policy=TransitionPolicy(allowed=PRESETS.get(style, PRESETS["minimal"])), style=style)
    total_frames = max(item.end_frame for item in timeline)
    adapted = audio_dir / "bgm_adapted.wav"
    adapt_audio_to_duration(copied_audio, total_frames / fps, adapted)
    output = VideoOutput(project_dir=str(project_dir.resolve()), render_data=str((project_dir / "render_data.json").resolve()), final_video=str((project_dir / "render" / "final.mp4").resolve()))
    project = VideoProject(project_id=session_id, fps=fps, width=width, height=height, images=assets, audio=AudioConfig(path="audio/bgm_adapted.wav", source_path=f"audio/{source_audio.name}", duration=total_frames / fps, sample_rate=analysis.sample_rate, bpm=analysis.bpm), timeline=timeline, output=output)
    _write_render_data(project)
    session = ProjectSession(session_id=session_id, project_dir=str(project_dir.resolve()), images_dir=str(images_root), audio_path=str(source_audio), source_audio_path=str(copied_audio.resolve()), output_dir=str(output_root), width=width, height=height, fps=fps, style=style, project=project, beat_analysis=BeatAnalysisSession.from_analysis(analysis), image_analysis=[analyze_asset(asset, str(project_dir)) for asset in assets], preview_path=str((project_dir / "render" / "preview.mp4").resolve()), final_video_path=output.final_video)
    session.save()
    return session


def load_project_session(project_dir: str | Path) -> ProjectSession:
    root = Path(project_dir).resolve()
    path = root / "session.json"
    if not path.is_file():
        raise FileNotFoundError(f"Project session does not exist: {path}")
    session = ProjectSession.model_validate_json(path.read_text(encoding="utf-8"))
    for value in (session.project_dir, session.images_dir, session.audio_path, session.source_audio_path, session.output_dir):
        if not Path(value).is_absolute():
            raise ValueError(f"Session path must be absolute: {value}")
    return session
