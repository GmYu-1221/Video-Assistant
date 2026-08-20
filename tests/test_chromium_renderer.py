import json
import shutil
import subprocess
from pathlib import Path

import pytest

from content_creator.schemas import AnimationArtifact
from content_creator.services.renderer import ChromiumRenderer


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="FFmpeg is required")
def test_four_frames_pipe_to_mp4_with_bgm(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    source_runtime = Path(__file__).resolve().parents[1] / "src" / "content_creator" / "runtime" / "gsap.min.js"
    shutil.copy2(source_runtime, runtime / "gsap.min.js")
    html = """<!doctype html><html><head><style>html,body{margin:0;width:64px;height:64px;background:#000}#box{width:20px;height:20px;background:#fff}</style><script src="runtime/gsap.min.js"></script></head><body><div id="box"></div><script>
window.__ANIMATION_READY__=false;window.__ANIMATION_META__={width:64,height:64,fps:30,durationFrames:4};
const masterTimeline=gsap.timeline({paused:true});masterTimeline.to('#box',{x:40,duration:0.1});
window.renderFrame=async function(frame){const fps=window.__ANIMATION_META__.fps;const time=frame/fps;masterTimeline.time(time,false);await document.fonts.ready};
document.fonts.ready.then(()=>window.__ANIMATION_READY__=true);
</script></body></html>"""
    (tmp_path / "animation.html").write_text(html, encoding="utf-8")
    bgm = tmp_path / "audio" / "bgm_adapted.wav"
    bgm.parent.mkdir()
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.14", str(bgm)], check=True)
    artifact = AnimationArtifact(html_path=str(tmp_path / "animation.html"), model="test", width=64, height=64, fps=30, duration_frames=4, prompt_path=str(tmp_path / "prompt.json"))
    try:
        output = ChromiumRenderer().render(artifact, tmp_path, bgm, tmp_path / "render" / "final.mp4")
    except Exception as exc:
        if "Executable doesn't exist" in str(exc) or "Permission denied" in str(exc):
            pytest.skip("Playwright Chromium is not installed")
        raise
    assert output.is_file()
    assert not list(tmp_path.rglob("*.png"))
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name", "-of", "json", str(output)], capture_output=True, text=True, check=True)
    streams = json.loads(probe.stdout)["streams"]
    assert any(item["codec_type"] == "video" and item["codec_name"] == "h264" for item in streams)
    assert any(item["codec_type"] == "audio" and item["codec_name"] == "aac" for item in streams)
