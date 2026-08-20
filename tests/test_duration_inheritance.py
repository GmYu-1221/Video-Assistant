import json
from pathlib import Path
from types import SimpleNamespace

from content_creator.schemas import AnimationArtifact, ProjectContext
from content_creator.services import url_video


def test_bgm_renderer_and_final_validation_inherit_artifact_duration(tmp_path, monkeypatch):
    for directory in ("audio", "render"):
        (tmp_path / directory).mkdir()
    context = ProjectContext(project_id="p", project_dir=str(tmp_path), urls=["https://example.com"])
    artifact = AnimationArtifact(
        html_path=str(tmp_path / "animation.html"), model="test", width=1080, height=1920,
        fps=30, duration_frames=450, prompt_path=str(tmp_path / "animation_prompt.json"),
    )
    calls = {}
    track = SimpleNamespace(id="bgm", path="source.wav", license_note="test")
    monkeypatch.setattr(url_video, "load_catalog", lambda _root: [track])
    monkeypatch.setattr(url_video, "select_track", lambda _tracks, _mood, _topics: track)

    def adapt(_source, duration, output):
        calls["bgm_duration"] = duration
        Path(output).write_bytes(b"audio")
        return Path(output)

    class Renderer:
        def render(self, received_artifact, _project_dir, _bgm, output, on_progress=None):
            calls["render_frames"] = received_artifact.duration_frames
            Path(output).write_bytes(b"video")

    def validate(_output, **expected):
        calls["validation_duration"] = expected["duration_seconds"]
        return {"passed": True, "errors": []}

    monkeypatch.setattr(url_video, "adapt_audio_to_duration", adapt)
    monkeypatch.setattr(url_video, "ChromiumRenderer", Renderer)
    monkeypatch.setattr(url_video, "validate_final_artifact", validate)
    output = url_video.render_animation(artifact, {
        "project": context,
        "editorial_plan": SimpleNamespace(mood="informative", topics=[]),
    })

    assert output == tmp_path / "render" / "final.mp4"
    assert calls == {"bgm_duration": 15.0, "render_frames": 450, "validation_duration": 15.0}
    selection = json.loads((tmp_path / "audio" / "selection.json").read_text(encoding="utf-8"))
    assert selection["duration_seconds"] == 15.0
