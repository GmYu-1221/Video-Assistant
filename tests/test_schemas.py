from content_creator.schemas import *

def test_project_schema():
    project = VideoProject(project_id='x', images=[ImageAsset(id='a', filename='a.jpg', relative_path='materials/a.jpg', width=1, height=1)], audio=AudioConfig(path='audio/a.wav', duration=1, sample_rate=44100), timeline=[TimelineItem(asset_id='a', start_frame=0, end_frame=30, duration_frames=30, transition=TransitionConfig())], output=VideoOutput(project_dir='x', render_data='x/render_data.json', final_video='x/render/final.mp4'))
    assert project.fps == 30
