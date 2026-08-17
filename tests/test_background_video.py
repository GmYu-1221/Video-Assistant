import json
import random
from pathlib import Path
from types import SimpleNamespace

import pytest

from content_creator.services import url_video


def test_background_video_prefers_mp4_and_persists_one_random_choice(tmp_path, monkeypatch):
    source = tmp_path / "sources"
    source.mkdir()
    (source / "duplicate.mov").write_bytes(b"mov")
    (source / "one.mp4").write_bytes(b"one")
    (source / "two.mp4").write_bytes(b"two")

    payload = {"streams": [{"width": 1920, "height": 3414}], "format": {"duration": "9.25"}}
    seen = []

    def probe(command, **_kwargs):
        seen.append(Path(command[-1]).name)
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload))

    monkeypatch.setattr(url_video.subprocess, "run", probe)
    project = tmp_path / "project"
    config = url_video._select_background_video(source, project, rng=random.Random(4))
    assert config.source_filename in {"one.mp4", "two.mp4"}
    assert config.source_filename != "duplicate.mov"
    assert seen == [config.source_filename]
    assert config.duration == 9.25
    assert config.loop is True and config.muted is True
    assert (project / config.path).read_bytes() in {b"one", b"two"}


def test_background_video_directory_must_contain_supported_media(tmp_path):
    (tmp_path / "readme.txt").write_text("none", encoding="utf-8")
    with pytest.raises(ValueError, match="没有可用视频"):
        url_video._select_background_video(tmp_path, tmp_path / "project")
