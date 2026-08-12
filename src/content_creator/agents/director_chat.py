"""Incremental DirectorPlan editing for the interactive Director CLI."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from content_creator.schemas import AnimationIntent, DirectorIntent, DirectorPlan, TransitionType
from content_creator.services.director.transition_policy import apply_transition_policy
from content_creator.services.llm.router import get_agent_provider


@dataclass
class DirectorSession:
    images: list[dict]
    beat_analysis: object
    style: str = "cinematic"
    current_plan: DirectorPlan | None = None
    conversation_history: list[dict[str, str]] = field(default_factory=list)
    intents: list[DirectorIntent] = field(default_factory=list)


def _fallback_intent(text: str, plan: DirectorPlan) -> DirectorIntent:
    lowered = text.lower()
    first = any(token in text for token in ("第一", "首张", "首张图片", "first"))
    target = 0 if first else None
    if any(token in lowered for token in ("背后翻转", "翻转进入", "flip in", "3d")) or "翻转" in text:
        return DirectorIntent(
            target_index=target if target is not None else 0,
            animation_intent=AnimationIntent(type="3d_flip_in", direction="back_to_front", camera_motion="rotation", speed="medium", emotion="cinematic", duration_frames=18),
            response="已将第一张图片标记为从背后翻转进入。",
        )
    if any(token in lowered for token in ("快一点", "更快", "faster", "quick")) or "快" in text:
        return DirectorIntent(transition_duration_frames=5, response="已将当前转场速度调整为快速。")
    if any(token in lowered for token in ("炸裂", "高潮", "爆发", "high energy", "climax")):
        return DirectorIntent(energy="high", response="已将高潮段落提升为高能转场。")
    return DirectorIntent(response="我理解了你的要求，但没有找到可安全修改的导演参数。")


def _intent_prompt(session: DirectorSession, text: str) -> str:
    return json.dumps({
        "task": "Return one JSON DirectorIntent delta for the current plan.",
        "current_plan": session.current_plan.model_dump(mode="json") if session.current_plan else None,
        "user_message": text,
        "output": {"target_index": "zero-based scene index", "animation_intent": "optional", "transition_duration_frames": "optional", "energy": "low|medium|high", "response": "short Chinese or English acknowledgement"},
        "rules": ["JSON only", "Never return React, TSX, Remotion code, ffmpeg, crop, cover, scaleX, or scaleY", "Only express director intent deltas"],
    }, ensure_ascii=False)


def _parse_intent(raw: str, fallback: DirectorIntent) -> DirectorIntent:
    if any(token in raw.lower() for token in ("tsx", "react", "object-fit", "cover", "crop", "scalex", "scaley", "ffmpeg")):
        return fallback
    try:
        return DirectorIntent.model_validate(json.loads(raw))
    except (ValueError, TypeError, json.JSONDecodeError):
        return fallback


def _apply_energy(plan: DirectorPlan) -> DirectorPlan:
    types = [TransitionType.whip, TransitionType.glitch, TransitionType.flash]
    items = []
    durations = {TransitionType.whip: 5, TransitionType.glitch: 5, TransitionType.flash: 3}
    for index, item in enumerate(plan.timeline):
        transition_type = types[index % len(types)]
        transition = item.transition.model_copy(update={"type": transition_type, "duration_frames": durations[transition_type]})
        items.append(item.model_copy(update={"transition": transition}))
    return apply_transition_policy(plan.model_copy(update={"timeline": items}), seed=0)


def apply_intent(plan: DirectorPlan, intent: DirectorIntent) -> DirectorPlan:
    """Apply only validated deltas; invalid targets leave the plan unchanged."""
    updated = plan
    if intent.target_index is not None and 0 <= intent.target_index < len(plan.timeline) and intent.animation_intent:
        item = plan.timeline[intent.target_index]
        updated_item = item.model_copy(update={"animation_intent": intent.animation_intent, "reason": intent.response})
        updated = plan.model_copy(update={"timeline": [updated_item if i == intent.target_index else value for i, value in enumerate(plan.timeline)]})
    if intent.transition_duration_frames is not None:
        updated = updated.model_copy(update={"timeline": [item.model_copy(update={"transition": item.transition.model_copy(update={"duration_frames": min(intent.transition_duration_frames, 8)})}) for item in updated.timeline]})
    if intent.energy == "high":
        updated = _apply_energy(updated)
    return updated


def handle_message(session: DirectorSession, text: str) -> tuple[DirectorSession, str]:
    provider = get_agent_provider("chat")
    fallback = _fallback_intent(text, session.current_plan or DirectorPlan(timeline=[]))
    intent = fallback
    if provider.model_name != "mock" and session.current_plan:
        try:
            intent = _parse_intent(provider.complete(_intent_prompt(session, text)), fallback)
        except Exception:
            intent = fallback
    if session.current_plan:
        session.current_plan = apply_intent(session.current_plan, intent)
    session.intents.append(intent)
    session.conversation_history.extend([{"role": "user", "content": text}, {"role": "assistant", "content": intent.response}])
    return session, intent.response
