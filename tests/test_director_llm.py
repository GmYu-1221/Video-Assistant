from content_creator.schemas import ScenePlan, Storyboard
from content_creator.services.llm.validator import validate_storyboard_json

def test_director_llm_json_becomes_storyboard():
    fallback = Storyboard(scenes=[ScenePlan(scene_id="001", asset_id="a", duration_frames=60)])
    raw = '{"style":"cinematic","scenes":[{"scene_id":"001","asset_id":"a","duration_frames":90,"entrance":{"type":"fade"},"motion":{"type":"static"},"transition":{"type":"fade","duration_frames":6,"direction":"from-right","intensity":0.6,"easing":"easeInOut"},"emotion":"dramatic"}]}'
    assert validate_storyboard_json(raw, fallback).scenes[0].duration_frames == 90
