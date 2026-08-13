from pathlib import Path

from content_creator.agents.director_chat import format_plan
from content_creator.schemas import DirectorPlan


class Session:
    fps = 30
    current_plan = DirectorPlan.model_validate({"timeline": [{
        "asset_id": "image-001", "duration_frames": 60,
        "transition": {"type": "crossfade", "duration_frames": 8},
        "reason": "opening",
        "transition_intent": {"description": "玻璃碎裂展开到下一张"},
    }]})


def test_show_separates_baseline_and_creative_transition():
    output = format_plan(Session())
    assert "Transition: crossfade / 8f (baseline)" in output
    assert "Creative Transition: 玻璃碎裂展开到下一张" in output


def test_architecture_document_describes_single_visual_agent():
    document = Path("docs/architecture_final.md").read_text(encoding="utf-8")
    assert "one Remotion Creative Agent" in document
    assert "TransitionEffectRenderer" in document
