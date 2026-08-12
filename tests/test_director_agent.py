from argparse import Namespace
from content_creator.agents.director_agent import build_storyboard
from content_creator.schemas import AudioConfig, ImageAsset, RGBColor, TimelineItem, TransitionConfig, VideoOutput, VideoProject

def test_director_defaults_to_static_motion():
    asset = ImageAsset(id="a", filename="a.jpg", relative_path="materials/a.jpg", width=100, height=100, backgroundColor=RGBColor(r=1,g=2,b=3))
    project = VideoProject(project_id="x", images=[asset], audio=AudioConfig(path="audio/a.wav", duration=1, sample_rate=44100), timeline=[TimelineItem(asset_id="a", start_frame=0, end_frame=30, duration_frames=30, transition=TransitionConfig())], output=VideoOutput(project_dir=".", render_data="render_data.json", final_video="render/final.mp4"))
    board = build_storyboard({"project": project, "style": "minimal"})
    assert board.scenes[0].motion.type == "static"
