from pathlib import Path
from content_creator.agents.remotion_agent import build_advice, load_skill_documents
from content_creator.schemas import Storyboard, ScenePlan

def test_remotion_agent_reads_official_skill_documents():
    documents = load_skill_documents()
    assert len(documents) == 4
    assert all(Path(document).name == "SKILL.md" for document in documents)

def test_remotion_advice_enforces_existing_rendering_rules():
    advice = build_advice({"storyboard": Storyboard(scenes=[ScenePlan(scene_id="001", asset_id="image-001", duration_frames=60)])})
    assert advice.image_fit == "contain"
    assert advice.motion_default == "static"
    assert advice.transition_registry_required
