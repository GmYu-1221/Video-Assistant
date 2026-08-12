from pathlib import Path

import pytest
from pydantic import ValidationError

from content_creator.schemas import TransitionConfig, TransitionType


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_static_image_frame_has_no_axis_distortion() -> None:
    source = (REPO_ROOT / "remotion/src/components/ImageFrame.tsx").read_text(encoding="utf-8")
    assert "scaleX(" not in source
    assert "scaleY(" not in source
    assert "object-fit: cover" not in source


def test_stretch_whip_explicitly_allows_distortion() -> None:
    config = TransitionConfig(type=TransitionType.stretch_whip, duration_frames=6, allow_distortion=True)
    assert config.allow_distortion is True
    source = (REPO_ROOT / "remotion/src/transitions/presentations/stretch_whip.tsx").read_text(encoding="utf-8")
    assert "scaleX(" in source
    assert "filter:" in source


def test_regular_fade_rejects_distortion() -> None:
    with pytest.raises(ValidationError, match="allow_distortion"):
        TransitionConfig(type=TransitionType.fade, allow_distortion=True)


def test_stretch_whip_returns_neutral_scene_at_completion() -> None:
    source = (REPO_ROOT / "remotion/src/transitions/presentations/stretch_whip.tsx").read_text(encoding="utf-8")
    assert "if (presentationProgress >= 1) return <AbsoluteFill>{children}</AbsoluteFill>;" in source
    assert "scaleX = entering ? 0.6 + presentationProgress * 0.4 : 1 + eased * 0.35" in source


def test_next_static_scene_still_uses_contain_image_frame() -> None:
    source = (REPO_ROOT / "remotion/src/Composition.tsx").read_text(encoding="utf-8")
    assert "<ImageFrame" in source
    image_frame = (REPO_ROOT / "remotion/src/components/ImageFrame.tsx").read_text(encoding="utf-8")
    assert "const fitScale = Math.min(videoWidth / imageWidth, videoHeight / imageHeight);" in image_frame
