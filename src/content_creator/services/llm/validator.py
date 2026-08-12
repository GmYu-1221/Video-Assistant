import json
import re

from pydantic import ValidationError

from content_creator.schemas import DirectorPlan, DirectorPlanPatch, Storyboard
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


def validate_director_plan_patch_json(raw: str, asset_ids: list[str]) -> DirectorPlanPatch:
    """Validate a narrow Chat response without touching the current plan."""
    if any(token in raw.lower() for token in _FORBIDDEN):
        raise ValueError("Patch contains prohibited implementation or image-processing content")
    try:
        payload = _extract_director_plan_patch_payload(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Patch JSON cannot be parsed; return one JSON object only") from exc

    if "timeline" in payload:
        raise ValueError("Patch must contain operations, not a complete DirectorPlan")
    if "operations" not in payload:
        raise ValueError("Patch is missing required field: operations")
    unknown_top_level = set(payload) - {"operations"}
    if unknown_top_level:
        raise ValueError(f"Patch contains unknown top-level field: {sorted(unknown_top_level)[0]}")
    try:
        patch = DirectorPlanPatch.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(_format_patch_validation_error(exc)) from exc
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Patch validation failed: {exc}") from exc

    known = set(asset_ids)
    seen: set[str] = set()
    for operation in patch.operations:
        if operation.scene_id not in known:
            raise ValueError(f"Unknown scene_id: {operation.scene_id}. Valid asset_ids: {', '.join(asset_ids)}")
        if operation.scene_id in seen:
            raise ValueError(f"Duplicate scene_id in patch: {operation.scene_id}")
        seen.add(operation.scene_id)
    return patch


_JSON_FENCE = re.compile(r"\A\s*```(?:json)?\s*\n(?P<payload>.*?)\n?```\s*\Z", re.DOTALL | re.IGNORECASE)


def _extract_director_plan_patch_payload(raw: str) -> dict:
    """Accept exactly one object, optionally enclosed by one JSON Markdown fence."""
    candidate = raw.strip()
    fenced = _JSON_FENCE.fullmatch(raw)
    if fenced:
        candidate = fenced.group("payload").strip()
    payload = json.loads(candidate)
    if not isinstance(payload, dict):
        raise TypeError("Patch root must be a JSON object")
    return payload


def _format_patch_validation_error(exc: ValidationError) -> str:
    error = exc.errors()[0]
    location = ".".join(str(part) for part in error["loc"])
    message = error["msg"]
    if location.endswith("creative_intent.description") and error["type"] == "missing":
        return "Patch is missing required field: creative_intent.description"
    if location.endswith("changes") and "at least one field" in message:
        return "Patch operation changes cannot be empty"
    if location.endswith("creative_intent") and "cannot be null" in message:
        return "Patch creative_intent cannot be null"
    if ".transition.type" in location:
        return f"Invalid transition type at {location}: {message}"
    if ".transition.duration_frames" in location:
        return f"Invalid transition duration_frames at {location}: {message}"
    return f"Patch validation failed at {location}: {message}"
