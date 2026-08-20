import re
from pathlib import Path

import pytest

from content_creator.services.html_validator import AnimationHTMLValidationError, extract_complete_html, validate_animation_html


def valid_html() -> str:
    return """<!doctype html><html><head><script src="runtime/gsap.min.js"></script></head><body>
<div id="box"></div><script>
window.__ANIMATION_READY__ = false;
window.__ANIMATION_META__ = {fps: 30, durationFrames: 4, width: 64, height: 64};
const masterTimeline = gsap.timeline({paused: true});
masterTimeline.to('#box', {x: 20, duration: 0.1});
window.renderFrame = async function(frame) { const fps=window.__ANIMATION_META__.fps; const time=frame/fps; masterTimeline.time(time, false); await document.fonts.ready; };
Promise.all([document.fonts.ready]).then(() => { window.__ANIMATION_READY__ = true; });
</script></body></html>"""


def project(tmp_path: Path) -> Path:
    (tmp_path / "runtime").mkdir()
    (tmp_path / "runtime" / "gsap.min.js").write_text("gsap", encoding="utf-8")
    return tmp_path


def test_complete_html_generates_valid_contract(tmp_path):
    html = extract_complete_html("```html\n" + valid_html() + "\n```")
    validate_animation_html(html, project(tmp_path), width=64, height=64, fps=30, duration_frames=4)


@pytest.mark.parametrize("replacement", [
    "masterTimeline.time(frame / fps, false)",
    "masterTimeline.time(\n  frame / window.__ANIMATION_META__.fps,\n  false\n)",
    "const seconds = frame / fps; masterTimeline.time(seconds, false)",
])
def test_equivalent_frame_derived_timeline_seek_is_accepted(tmp_path, replacement):
    html = valid_html().replace("masterTimeline.time(time, false)", replacement)
    validate_animation_html(html, project(tmp_path), width=64, height=64, fps=30, duration_frames=4)


@pytest.mark.parametrize("replacement,detail", [
    ("masterTimeline.seek(time)", "found masterTimeline.seek"),
    ("masterTimeline.time(time)", "must use frame/fps and pass false"),
    ("masterTimeline.time(1, false)", "must use frame/fps and pass false"),
])
def test_non_contract_timeline_seek_is_rejected_with_detail(tmp_path, replacement, detail):
    html = valid_html().replace("masterTimeline.time(time, false)", replacement)
    with pytest.raises(AnimationHTMLValidationError, match=re.escape(detail)):
        validate_animation_html(html, project(tmp_path), width=64, height=64, fps=30, duration_frames=4)


@pytest.mark.parametrize("needle,replacement", [
    ("runtime/gsap.min.js", "runtime/missing.js"),
    ("const masterTimeline", "const timeline"),
    ("window.renderFrame", "window.draw"),
    ("window.__ANIMATION_READY__", "window.ready"),
    ("window.__ANIMATION_META__", "window.meta"),
])
def test_missing_contract_parts_fail(tmp_path, needle, replacement):
    with pytest.raises(AnimationHTMLValidationError):
        validate_animation_html(valid_html().replace(needle, replacement), project(tmp_path), width=64, height=64, fps=30, duration_frames=4)


@pytest.mark.parametrize("payload", [
    '<img src="https://example.com/a.png">', '<script>fetch("x")</script>',
    '<script>new XMLHttpRequest()</script>', '<script>new WebSocket("x")</script>',
    '<iframe src="materials/a"></iframe>', '<script>import("x")</script>',
    '<script>eval("x")</script>', '<img src="../secret.png">',
])
def test_unsafe_html_is_rejected(tmp_path, payload):
    with pytest.raises(AnimationHTMLValidationError):
        validate_animation_html(valid_html().replace("<div id=\"box\"></div>", payload), project(tmp_path), width=64, height=64, fps=30, duration_frames=4)
