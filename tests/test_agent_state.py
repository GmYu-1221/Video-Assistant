from content_creator.workflow.state import VideoState

def test_state_shape_accepts_workflow_fields():
    state: VideoState = {"errors": [], "style": "minimal"}
    assert state["errors"] == []
