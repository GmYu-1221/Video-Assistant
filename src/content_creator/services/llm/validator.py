import json

from content_creator.schemas import DirectorPlan, Storyboard
from content_creator.services.timeline.slideshow_builder import REAL_TRANSITIONS

_FORBIDDEN = ("tsx", "object-fit", "cover", "crop", "scalex", "scaley")

def validate_storyboard_json(raw: str, fallback: Storyboard) -> Storyboard:
    try:
        if any(token in raw.lower() for token in _FORBIDDEN): return fallback
        payload = json.loads(raw)
        storyboard = Storyboard.model_validate(payload)
        if any(scene.motion.type != "static" or scene.transition.type not in REAL_TRANSITIONS for scene in storyboard.scenes): return fallback
        return storyboard
    except (ValueError, TypeError, json.JSONDecodeError):
        return fallback


def validate_director_plan_json(raw: str, fallback: DirectorPlan, asset_ids: list[str]) -> DirectorPlan:
    """Reject LLM output that is unsafe, incomplete, out of order, or unrenderable."""
    try:
        if any(token in raw.lower() for token in _FORBIDDEN):
            return fallback
        plan = DirectorPlan.model_validate(json.loads(raw))
        if [item.asset_id for item in plan.timeline] != asset_ids:
            return fallback
        if any(item.motion != "static" or item.transition.type not in REAL_TRANSITIONS for item in plan.timeline):
            return fallback
        return plan
    except (ValueError, TypeError, json.JSONDecodeError):
        return fallback
