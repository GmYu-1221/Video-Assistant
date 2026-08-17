import json

import pytest

from content_creator.services.music.catalog import load_catalog


def test_music_catalog_uses_only_configured_library_and_discovers_new_tracks(tmp_path):
    root = tmp_path / "project"
    music = tmp_path / "music"
    tracks = music / "tracks"
    tracks.mkdir(parents=True)
    catalogued = tracks / "catalogued.mp3"
    discovered = tracks / "new-song.mp3"
    catalogued.write_bytes(b"audio")
    discovered.write_bytes(b"audio")
    (music / "catalog.json").write_text(json.dumps([{
        "id": "catalogued", "path": str(catalogued), "moods": ["tech"],
        "topics": ["ai"], "energy": .8,
    }]), encoding="utf-8")

    result = load_catalog(root, music)

    assert {track.id for track in result} == {"catalogued", "local-tracks-new-song"}
    assert all(str(music.resolve()) in track.path for track in result)


def test_music_catalog_does_not_fall_back_outside_configured_library(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "input").mkdir()
    (root / "input" / "bgm.wav").write_bytes(b"legacy")
    music = tmp_path / "empty-music"
    music.mkdir()

    with pytest.raises(ValueError, match="背景音乐目录中没有可用音频"):
        load_catalog(root, music)
