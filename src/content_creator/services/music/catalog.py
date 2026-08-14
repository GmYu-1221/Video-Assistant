"""Local, tag-driven BGM catalog selection."""
from __future__ import annotations

import json
from pathlib import Path

from content_creator.schemas import MusicTrack


def load_catalog(project_root: str | Path) -> list[MusicTrack]:
    root = Path(project_root)
    path = root / "input" / "music" / "catalog.json"
    if path.is_file():
        try:
            tracks = [MusicTrack.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))]
            usable = [track for track in tracks if (root / track.path).is_file()]
            if usable:
                return usable
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
    return [MusicTrack(id="default", path="input/bgm.wav", moods=["informative"], topics=[], energy=0.55, license_note="Project default track")]


def select_track(tracks: list[MusicTrack], mood: str, topics: list[str]) -> MusicTrack:
    normalized = {topic.lower() for topic in topics}
    def score(track: MusicTrack) -> tuple[float, str]:
        matches = len(normalized.intersection(item.lower() for item in track.topics))
        mood_score = 2 if mood.lower() in {item.lower() for item in track.moods} else 0
        return (matches * 3 + mood_score + track.energy * 0.01, track.id)
    return max(tracks, key=score)
