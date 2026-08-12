"""Plan-first Director Workspace interactions; no Remotion source generation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from content_creator.agents.director_agent import create_director_plan, plan_to_storyboard
from content_creator.schemas import AnimationIntent, DirectorIntent, DirectorPlan
from content_creator.services.director.transition_policy import apply_transition_policy
from content_creator.services.llm.router import get_agent_provider
from content_creator.services.llm.validator import validate_director_plan_json
from content_creator.sessions.project_session import ProjectSession


_FORBIDDEN = ("tsx", "react", "object-fit", "cover", "crop", "scalex", "scaley", "ffmpeg", "css")


@dataclass
class DirectorSession:
    """Backward-compatible lightweight session used by library callers."""

    images: list[dict]
    beat_analysis: object
    style: str = "cinematic"
    current_plan: DirectorPlan | None = None
    conversation_history: list[dict[str, str]] = field(default_factory=list)


def _chat_prompt(session: ProjectSession, message: str) -> str:
    return json.dumps({
        "role": "short-form video director",
        "task": "Update the existing DirectorPlan. Return ONLY complete DirectorPlan JSON.",
        "project": {"style": session.style, "images": [asset.model_dump(mode="json") for asset in session.project.images], "beat_analysis": session.beat_analysis.model_dump(mode="json")},
        "current_plan": session.current_plan.model_dump(mode="json") if session.current_plan else None,
        "recent_history": session.conversation_history[-10:],
        "user_feedback": message,
        "rules": [
            "Prefer local edits. Keep scenes that the user did not mention unchanged.",
            "Preserve asset order and return one item per image.",
            "motion must remain static.",
            "For entrance requests use animation_intent only; never return TSX, React, CSS, ffmpeg, crop, cover, scaleX or scaleY.",
            "Use beat and downbeat information for pacing. Use only supported TransitionConfig types.",
        ],
    }, ensure_ascii=False)


def _scene_index(message: str) -> int | None:
    chinese = re.search(r"第\s*([一二三四五六七八九十]|\d+)\s*张", message)
    english = re.search(r"\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\b", message.lower())
    values = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "七": 6, "八": 7, "九": 8, "十": 9, "first": 0, "second": 1, "third": 2, "fourth": 3, "fifth": 4, "sixth": 5, "seventh": 6, "eighth": 7, "ninth": 8, "tenth": 9}
    if chinese:
        token = chinese.group(1)
        return values[token] if token in values else int(token) - 1
    return values[english.group(1)] if english else None


def _local_update(session: ProjectSession, message: str) -> tuple[DirectorPlan, str]:
    plan = session.current_plan
    if plan is None:
        plan = create_director_plan(session.project.images, session.beat_analysis.to_analysis(), session.style)
    lowered = message.lower()
    index = _scene_index(message)
    if any(key in message for key in ("翻转", "背面", "卡片")) or "flip" in lowered:
        target = 0 if index is None else index
        if not 0 <= target < len(plan.timeline):
            return plan, "未找到指定场景，当前计划未修改。"
        intent = AnimationIntent(type="3d_card_flip", direction="back_to_front", speed="medium", duration_frames=18, energy=0.7, camera_motion="orbit", visual_effects=[], description="Image starts showing its back side and rotates around the Y axis until the full front face settles.")
        item = plan.timeline[target].model_copy(update={"animation_intent": intent})
        return plan.model_copy(update={"timeline": [item if i == target else existing for i, existing in enumerate(plan.timeline)]}), f"已修改 Scene {target + 1:02d}\n入场：fade -> 3d_card_flip（背后翻转）\n方向：back_to_front\n时长：18 frames"
    if any(key in message for key in ("增加50%", "延长50%")) and index is not None and 0 <= index < len(plan.timeline):
        item = plan.timeline[index]
        updated = item.model_copy(update={"duration_frames": round(item.duration_frames * 1.5)})
        return plan.model_copy(update={"timeline": [updated if i == index else existing for i, existing in enumerate(plan.timeline)]}), f"已将 Scene {index + 1:02d} 停留时间增加 50%。"
    if any(key in message for key in ("快一点", "更快", "强拍")) or "faster" in lowered:
        timeline = [item.model_copy(update={"transition": item.transition.model_copy(update={"duration_frames": min(item.transition.duration_frames, 5)})}) for item in plan.timeline]
        return plan.model_copy(update={"timeline": timeline}), "已将转场调整为快速节奏。"
    if any(key in message for key in ("高潮", "炸裂", "冲击")) or "climax" in lowered:
        energized = apply_transition_policy(plan, session.beat_analysis.beat_strengths, seed=2)
        if len(energized.timeline) == 1:
            from content_creator.schemas import TransitionConfig, TransitionType
            item = energized.timeline[0]
            energized = energized.model_copy(update={"timeline": [item.model_copy(update={"transition": TransitionConfig(type=TransitionType.glitch, duration_frames=5)})]})
        return energized, "已增强高潮转场能量，同时保持转场不连续重复。"
    if any(key in message for key in ("最后两张", "结尾放慢")):
        indices = range(max(0, len(plan.timeline) - 2), len(plan.timeline))
        timeline = [item.model_copy(update={"duration_frames": round(item.duration_frames * 1.5)}) if i in indices else item for i, item in enumerate(plan.timeline)]
        return plan.model_copy(update={"timeline": timeline}), "已放慢最后两张图片的节奏。"
    return plan, "已记录反馈，但未识别到可安全应用的局部导演修改。"


def generate_plan(session: ProjectSession, user_request: str = "") -> tuple[ProjectSession, str]:
    session.current_plan = create_director_plan(session.project.images, session.beat_analysis.to_analysis(), session.style)
    session.current_storyboard = plan_to_storyboard(session.current_plan, session.style)
    session.dirty = True
    text = "DirectorPlan 已生成并通过校验。"
    if user_request:
        session, feedback = update_plan(session, user_request)
        text = f"{text}\n{feedback}"
    return session, text


def update_plan(session: ProjectSession, message: str) -> tuple[ProjectSession, str]:
    if session.current_plan is None:
        return generate_plan(session, message)
    previous = session.current_plan
    provider = get_agent_provider("chat")
    updated, response = _local_update(session, message)
    if provider.model_name != "mock":
        try:
            raw = provider.complete(_chat_prompt(session, message))
            if not any(token in raw.lower() for token in _FORBIDDEN):
                candidate = validate_director_plan_json(raw, previous, [asset.id for asset in session.project.images])
                if candidate != previous:
                    updated = apply_transition_policy(candidate, session.beat_analysis.beat_strengths)
                    response = "已根据反馈更新当前 DirectorPlan。"
        except Exception:
            response = f"{response}\nLLM 调用失败，已使用安全本地修改。"
    session.current_plan = updated
    session.current_storyboard = plan_to_storyboard(updated, session.style)
    session.dirty = updated != previous
    session.conversation_history.extend([{"role": "user", "content": message}, {"role": "assistant", "content": response}])
    session.conversation_history = session.conversation_history[-20:]
    return session, response


def format_plan(session: ProjectSession, as_json: bool = False) -> str:
    if session.current_plan is None:
        return "当前还没有 DirectorPlan。输入 plan 生成初版方案。"
    if as_json:
        return session.current_plan.model_dump_json(indent=2)
    lines: list[str] = []
    for index, item in enumerate(session.current_plan.timeline, 1):
        intent = item.animation_intent.type if item.animation_intent else "fade"
        lines.extend([f"Scene {index:02d}", f"Asset: {item.asset_id}", f"Duration: {item.duration_frames} frames / {item.duration_frames / session.fps:.1f}s", f"Entrance: {intent}", f"Transition: {item.transition.type.value} / {item.transition.duration_frames}f", f"Emotion: {item.reason}", ""])
    return "\n".join(lines).rstrip()


def handle_message(session: DirectorSession, message: str) -> tuple[DirectorSession, str]:
    """Compatibility adapter for the pre-workspace DirectorSession API."""
    if session.current_plan is None:
        return session, "当前还没有 DirectorPlan。"
    # The local delta path is shared with the persistent workspace semantics.
    class _Compat:
        def __init__(self, owner: DirectorSession) -> None:
            self.current_plan = owner.current_plan
            self.style = owner.style
            self.fps = 30
            self.conversation_history = owner.conversation_history
            self.project = type("Project", (), {"images": []})()
            self.beat_analysis = type("Beat", (), {"beat_strengths": None, "model_dump": lambda self: {}})()

    compat = _Compat(session)
    updated, response = _local_update(compat, message)
    session.current_plan = updated
    # Preserve the legacy library adapter's historical intent name; the
    # persistent workspace uses the richer `3d_card_flip` intent unchanged.
    if session.current_plan and session.current_plan.timeline[0].animation_intent and session.current_plan.timeline[0].animation_intent.type == "3d_card_flip":
        intent = session.current_plan.timeline[0].animation_intent.model_copy(update={"type": "3d_flip_in"})
        item = session.current_plan.timeline[0].model_copy(update={"animation_intent": intent})
        session.current_plan = session.current_plan.model_copy(update={"timeline": [item, *session.current_plan.timeline[1:]]})
    session.conversation_history.extend([{"role": "user", "content": message}, {"role": "assistant", "content": response}])
    session.conversation_history = session.conversation_history[-20:]
    return session, response
