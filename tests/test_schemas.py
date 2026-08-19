import pytest

from content_creator.schemas import *

def test_project_schema():
    project = VideoProject(project_id='x', images=[ImageAsset(id='a', filename='a.jpg', relative_path='materials/a.jpg', width=1, height=1)], audio=AudioConfig(path='audio/a.wav', duration=1, sample_rate=44100), timeline=[TimelineItem(asset_id='a', start_frame=0, end_frame=30, duration_frames=30, transition=TransitionConfig())], output=VideoOutput(project_dir='x', render_data='x/render_data.json', final_video='x/render/final.mp4'))
    assert project.fps == 30
    assert project.video_copy.headline == ''
    assert project.images[0].entrance.type == "none"


def test_image_asset_rejects_removed_fade_entrance():
    with pytest.raises(ValueError, match="entrance"):
        ImageAsset(
            id="a",
            filename="a.jpg",
            relative_path="materials/a.jpg",
            width=1,
            height=1,
            entrance={"type": "fade", "durationInFrames": 15},
        )


def test_video_copy_rejects_overlong_text_and_too_many_lines():
    with pytest.raises(ValueError, match="headline"):
        VideoCopy(headline="\n".join(["一"] * 3))
    with pytest.raises(ValueError, match="body"):
        VideoCopy(body="\n".join(["一"] * 9))
    with pytest.raises(ValueError):
        VideoCopy(subtitle="一" * 41)
