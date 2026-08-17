"""Local, tag-driven BGM catalog selection."""
from __future__ import annotations

import json
import re
from pathlib import Path

from content_creator.schemas import MusicTrack

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}


def _resolve_track_path(project_root: Path, music_root: Path, value: str) -> Path | None:
    path = Path(value).expanduser()
    candidates = [path] if path.is_absolute() else [project_root / path, music_root / path]
    return next((candidate.resolve() for candidate in candidates if candidate.is_file()), None)


def _auto_track(music_root: Path, path: Path) -> MusicTrack:
    relative = path.relative_to(music_root)
    track_id = re.sub(r"[^a-z0-9]+", "-", relative.with_suffix("").as_posix().lower()).strip("-") or path.stem
    return MusicTrack(
        id=f"local-{track_id}", path=str(path.resolve()), moods=["informative"], topics=[],
        energy=.55, license_note="Uncatalogued local track; verify usage rights in input/music/CREDITS.txt",
    )


def load_catalog(project_root: str | Path, music_dir: str | Path | None = None) -> list[MusicTrack]:
    root = Path(project_root).resolve()
    music_root = Path(music_dir).expanduser().resolve() if music_dir else root / "input" / "music"
    catalog_path = music_root / "catalog.json"
    tracks: list[MusicTrack] = []
    catalogued_paths: set[Path] = set()
    if catalog_path.is_file():
        try:
            entries = [MusicTrack.model_validate(item) for item in json.loads(catalog_path.read_text(encoding="utf-8"))]
            for track in entries:
                resolved = _resolve_track_path(root, music_root, track.path)
                if resolved is not None and resolved.suffix.lower() in AUDIO_EXTENSIONS:
                    tracks.append(track.model_copy(update={"path": str(resolved)}))
                    catalogued_paths.add(resolved)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
    discovered = sorted(
        path.resolve() for path in music_root.rglob("*")
        if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
    )
    tracks.extend(_auto_track(music_root, path) for path in discovered if path not in catalogued_paths)
    if not tracks:
        raise ValueError(f"背景音乐目录中没有可用音频：{music_root}")
    return tracks


def select_track(tracks: list[MusicTrack], mood: str, topics: list[str]) -> MusicTrack:
    normalized = {topic.lower() for topic in topics}
    def score(track: MusicTrack) -> tuple[float, str]:
        matches = len(normalized.intersection(item.lower() for item in track.topics))
        mood_score = 2 if mood.lower() in {item.lower() for item in track.moods} else 0
        return (matches * 3 + mood_score + track.energy * 0.01, track.id)
    return max(tracks, key=score)
