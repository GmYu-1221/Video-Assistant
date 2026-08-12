from content_creator.agents.director_agent import build_storyboard, create_director_plan
from content_creator.services.llm.provider import MockLLMProvider
from content_creator.services.music.beat_detector import BeatAnalysis
from content_creator.schemas import AudioConfig, ImageAsset, RGBColor, TimelineItem, TransitionConfig, VideoOutput, VideoProject


class StubProvider:
    model_name = "test-director-model"

    def __init__(self, response: str) -> None:
        self.response = response

    def complete(self, _prompt: str) -> str:
        return self.response


def test_director_defaults_to_static_motion():
    asset = ImageAsset(id="a", filename="a.jpg", relative_path="materials/a.jpg", width=100, height=100, backgroundColor=RGBColor(r=1,g=2,b=3))
    project = VideoProject(project_id="x", images=[asset], audio=AudioConfig(path="audio/a.wav", duration=1, sample_rate=44100), timeline=[TimelineItem(asset_id="a", start_frame=0, end_frame=30, duration_frames=30, transition=TransitionConfig())], output=VideoOutput(project_dir=".", render_data="render_data.json", final_video="render/final.mp4"))
    board = build_storyboard({"project": project, "style": "minimal"})
    assert board.scenes[0].motion.type == "static"


def test_director_agent_validates_llm_timeline_json():
    assets = [
        ImageAsset(id="a", filename="a.jpg", relative_path="materials/a.jpg", width=100, height=100),
        ImageAsset(id="b", filename="b.jpg", relative_path="materials/b.jpg", width=100, height=100),
    ]
    response = '''{"timeline":[
        {"asset_id":"a","duration_frames":90,"transition":{"type":"fade","duration_frames":6},"transition_strength":0.2,"motion":"static","reason":"Opening image."},
        {"asset_id":"b","duration_frames":120,"transition":{"type":"push","duration_frames":6},"transition_strength":0.8,"motion":"static","reason":"Stronger beat."}
    ]}'''

    plan = create_director_plan(
        assets,
        BeatAnalysis(duration=10, sample_rate=44100, bpm=120, beats=[0, 0.5], downbeats=[0]),
        "dynamic",
        provider=StubProvider(response),
    )

    assert [item.asset_id for item in plan.timeline] == ["a", "b"]
    assert plan.timeline[1].transition.type.value == "push"
    assert plan.timeline[1].motion == "static"


def test_director_agent_rejects_unsafe_or_out_of_order_llm_output():
    asset = ImageAsset(id="a", filename="a.jpg", relative_path="materials/a.jpg", width=100, height=100)
    plan = create_director_plan(
        [asset],
        BeatAnalysis(duration=10, sample_rate=44100, bpm=120, beats=[], downbeats=[]),
        "minimal",
        provider=StubProvider('{"tsx":"object-fit: cover"}'),
    )

    assert plan.timeline[0].asset_id == "a"
    assert plan.timeline[0].motion == "static"
    assert plan.timeline[0].reason == "Rule-based pacing from the BGM beat grid."
