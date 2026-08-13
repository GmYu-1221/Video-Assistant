from content_creator.schemas import AudioConfig, ImageAsset, TimelineItem, TransitionConfig, VideoOutput, VideoProject, TransitionPreset, VisualSpecDecision, VisualSpecTransitionDecision
from content_creator.services.visual_spec_adapter import project_to_visual_spec


def test_legacy_project_adapter_builds_center_stage_flash_transitions(tmp_path):
    project = VideoProject(project_id="p", width=1080, height=1920, images=[ImageAsset(id="a", filename="a.jpg", relative_path="a.jpg", width=10, height=10), ImageAsset(id="b", filename="b.jpg", relative_path="b.jpg", width=10, height=10)], audio=AudioConfig(path="a.wav", duration=4, sample_rate=44100), timeline=[TimelineItem(asset_id="a", start_frame=0, end_frame=60, duration_frames=60, transition=TransitionConfig()), TimelineItem(asset_id="b", start_frame=60, end_frame=120, duration_frames=60, transition=TransitionConfig())], output=VideoOutput(project_dir=str(tmp_path), render_data="render.json", final_video="final.mp4"))
    spec = project_to_visual_spec(project)
    assert spec.layout.preset.value == "center_stage"
    assert spec.transitions[0].preset.value == "flash_zoom_blur"
    assert spec.transitions[0].start_frame == 49
    assert len(spec.transitions[0].tracks) == 4


def test_adapter_applies_validated_llm_decision(tmp_path):
    project = VideoProject(project_id="p", images=[ImageAsset(id="a", filename="a.jpg", relative_path="a.jpg", width=10, height=10), ImageAsset(id="b", filename="b.jpg", relative_path="b.jpg", width=10, height=10)], audio=AudioConfig(path="a.wav", duration=4, sample_rate=44100), timeline=[TimelineItem(asset_id="a", start_frame=0, end_frame=60, duration_frames=60, transition=TransitionConfig()), TimelineItem(asset_id="b", start_frame=60, end_frame=120, duration_frames=60, transition=TransitionConfig())], output=VideoOutput(project_dir=str(tmp_path), render_data="render.json", final_video="final.mp4"))
    decision = VisualSpecDecision(transitions=[VisualSpecTransitionDecision(from_asset_id="a", to_asset_id="b", preset=TransitionPreset.white_flash)])
    assert project_to_visual_spec(project, decision=decision).transitions[0].preset == TransitionPreset.white_flash
