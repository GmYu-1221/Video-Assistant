from content_creator.schemas import AudioConfig, ImageAsset, TimelineItem, TransitionConfig, VideoCopy, VideoOutput, VideoProject, TransitionPreset, VisualSpecDecision, VisualSpecTransitionDecision
from content_creator.services.visual_spec_adapter import project_to_visual_spec


def test_legacy_project_adapter_builds_center_stage_flash_transitions(tmp_path):
    project = VideoProject(project_id="p", width=1080, height=1920, images=[ImageAsset(id="a", filename="a.jpg", relative_path="a.jpg", width=10, height=10), ImageAsset(id="b", filename="b.jpg", relative_path="b.jpg", width=10, height=10)], audio=AudioConfig(path="a.wav", duration=4, sample_rate=44100), timeline=[TimelineItem(asset_id="a", start_frame=0, end_frame=60, duration_frames=60, transition=TransitionConfig()), TimelineItem(asset_id="b", start_frame=60, end_frame=120, duration_frames=60, transition=TransitionConfig())], output=VideoOutput(project_dir=str(tmp_path), render_data="render.json", final_video="final.mp4"))
    spec = project_to_visual_spec(project)
    assert spec.layout.preset.value == "center_stage"
    assert spec.transitions[0].preset.value == "flash_zoom_blur"
    assert spec.transitions[0].start_frame == 51
    assert spec.transitions[0].duration_frames == 9
    assert len(spec.transitions[0].tracks) == 4
    assert [(key.frame, key.value) for key in spec.scenes[0].layers[0].tracks[0].keyframes] == [(9, 1), (60, 1.025)]


def test_reference_layout_adds_fixed_copy_regions_and_one_late_peak(tmp_path):
    images = [ImageAsset(id=asset_id, filename=f"{asset_id}.jpg", relative_path=f"{asset_id}.jpg", width=10, height=10) for asset_id in "abcd"]
    timeline = [TimelineItem(asset_id=asset.id, start_frame=index * 60, end_frame=(index + 1) * 60, duration_frames=60, transition=TransitionConfig(intensity=intensity)) for index, (asset, intensity) in enumerate(zip(images, [.2, .4, .9, .6]))]
    project = VideoProject(project_id="p", width=1080, height=1920, images=images, audio=AudioConfig(path="a.wav", duration=8, sample_rate=44100), timeline=timeline, output=VideoOutput(project_dir=str(tmp_path), render_data="render.json", final_video="final.mp4"), video_copy=VideoCopy(headline="主标题", subtitle="副标题", body="第一行\n第二行"))
    spec = project_to_visual_spec(project)
    assert {name: region.model_dump() for name, region in spec.layout.regions.items()} == {"stage": {"x": 0, "y": 430, "width": 1080, "height": 610, "overflow": "hidden"}, "header": {"x": 60, "y": 120, "width": 960, "height": 260, "overflow": "visible"}, "footer": {"x": 80, "y": 1100, "width": 920, "height": 540, "overflow": "visible"}}
    assert [layer.id for layer in spec.persistent_layers] == ["headline", "subtitle", "body"]
    assert spec.persistent_layers[1].text_style.top_offset == 142
    assert [transition.preset.value for transition in spec.transitions] == ["flash_zoom_blur", "flash_zoom_blur", "vertical_stretch_blur"]


def test_adapter_applies_validated_llm_decision(tmp_path):
    project = VideoProject(project_id="p", images=[ImageAsset(id="a", filename="a.jpg", relative_path="a.jpg", width=10, height=10), ImageAsset(id="b", filename="b.jpg", relative_path="b.jpg", width=10, height=10)], audio=AudioConfig(path="a.wav", duration=4, sample_rate=44100), timeline=[TimelineItem(asset_id="a", start_frame=0, end_frame=60, duration_frames=60, transition=TransitionConfig()), TimelineItem(asset_id="b", start_frame=60, end_frame=120, duration_frames=60, transition=TransitionConfig())], output=VideoOutput(project_dir=str(tmp_path), render_data="render.json", final_video="final.mp4"))
    decision = VisualSpecDecision(transitions=[VisualSpecTransitionDecision(from_asset_id="a", to_asset_id="b", preset=TransitionPreset.white_flash)])
    assert project_to_visual_spec(project, decision=decision).transitions[0].preset == TransitionPreset.white_flash
