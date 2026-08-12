from content_creator.schemas import DirectorPlan
from content_creator.workflow.state import VideoState

def test_state_shape_accepts_workflow_fields():
    state: VideoState = {"errors": [], "style": "minimal"}
    assert state["errors"] == []


def test_state_supports_validated_director_plan():
    state: VideoState = {"director_plan": DirectorPlan.model_validate({"timeline": [{"asset_id": "a", "duration_frames": 30, "reason": "Test."}]})}
    assert state["director_plan"].timeline[0].motion == "static"
