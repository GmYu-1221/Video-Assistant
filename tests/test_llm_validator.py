from content_creator.schemas import ScenePlan, Storyboard
from content_creator.services.llm.validator import validate_storyboard_json

def test_validator_rejects_code_and_keeps_safe_fallback():
    fallback = Storyboard(scenes=[ScenePlan(scene_id="001", asset_id="a", duration_frames=60)])
    assert validate_storyboard_json('{"tsx":"object-fit:cover"}', fallback) == fallback
