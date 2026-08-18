from content_creator.main import apply_agent_workflow
from content_creator.schemas import AudioConfig, ImageAsset, TimelineItem, TransitionConfig, VideoOutput, VideoProject
from content_creator.services.music.beat_detector import BeatAnalysis


def test_agent_workflow_preserves_original_beat_analysis(monkeypatch):
    project = VideoProject(
        project_id="test",
        images=[
            ImageAsset(
                id="a",
                filename="a.jpg",
                relative_path="materials/a.jpg",
                width=100,
                height=100,
            )
        ],
        audio=AudioConfig(path="audio/bgm.wav", duration=4.0, sample_rate=44100, bpm=120.0),
        timeline=[
            TimelineItem(
                asset_id="a",
                start_frame=0,
                end_frame=120,
                duration_frames=120,
                transition=TransitionConfig(),
            )
        ],
        output=VideoOutput(
            project_dir=".",
            render_data="render_data.json",
            final_video="render/final.mp4",
        ),
    )
    analysis = BeatAnalysis(
        duration=4.0,
        sample_rate=44100,
        bpm=120.0,
        beats=[0.0, 0.5, 1.0, 1.5],
        downbeats=[0.0],
        beat_strengths=[0.2, 0.8, 0.4, 0.9],
    )
    captured = {}

    class FakeGraph:
        def invoke(self, state):
            captured.update(state)
            return {"project": state["project"]}

    monkeypatch.setattr("content_creator.workflow.build_graph", lambda: FakeGraph())

    result = apply_agent_workflow(project, analysis, "dynamic")

    assert result is project
    assert captured["beat_analysis"] is analysis
    assert captured["style"] == "dynamic"
    assert captured["errors"] == []
