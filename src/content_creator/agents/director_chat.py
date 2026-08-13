"""Project-session Director Chat using narrow, scene-addressed plan patches."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Callable

from content_creator.agents.director_agent import create_director_plan, load_remotion_skill_guidance, plan_to_storyboard
from content_creator.capabilities.visual_capability_catalog import DIRECTOR_VISUAL_CAPABILITIES, log_intent_adaptation
from content_creator.schemas import DirectorPlan, DirectorPlanPatch
from content_creator.services.llm.router import get_agent_provider
from content_creator.services.llm.validator import validate_director_plan_patch_json
from content_creator.sessions.project_session import ProjectSession


logger = logging.getLogger(__name__)
ProgressCallback = Callable[[str], None]
_SECRET = re.compile(r"(?i)(?:authorization\s*:\s*(?:bearer\s+)?|bearer\s+|api[_-]?key\s*[:=]\s*)[^\s,;]+")


def _chat_prompt(session: ProjectSession, message: str) -> str:
    """Request a small mergeable edit, never a replacement DirectorPlan."""
    return json.dumps(
        {
            "role": "short-form video director",
            "task": "Return ONLY DirectorPlanPatch JSON for the user's requested edits.",
            "project": {
                "style": session.style,
                "asset_ids": [asset.id for asset in session.project.images],
                "beat_analysis": session.beat_analysis.model_dump(mode="json"),
            },
            "current_plan": session.current_plan.model_dump(mode="json") if session.current_plan else None,
            "recent_history": session.conversation_history[-10:],
            "user_feedback": message,
            "remotion_capability_guidance": load_remotion_skill_guidance(),
            "available_visual_capabilities": DIRECTOR_VISUAL_CAPABILITIES,
            "output_contract": {
                "operations": [
                    {
                        "scene_id": "an existing asset_id exactly",
                        "changes": {
                            "creative_intent": {
                                "description": "visual director description",
                                "movement": "optional visual movement",
                                "camera": "optional camera direction",
                                "effects": ["descriptive visual layers"],
                                "timing": "optional timing",
                                "energy": 0.5,
                                "emotion": "optional emotional tone",
                                "style": "optional style",
                            },
                            "duration_frames": "optional positive integer",
                            "transition_intent": {"description": "natural-language visual transition to the following scene", "effects": ["descriptive visual layers"]},
                            "emotion": "optional scene rationale/emotion",
                            "timing": "optional scene timing note",
                        },
                    }
                ]
            },
            "minimal_example": {
                "operations": [{
                    "scene_id": "image-001",
                    "changes": {"creative_intent": {
                        "description": "Image enters through a cinematic particle assembly",
                        "movement": "upward reveal",
                        "camera": "subtle perspective push",
                        "effects": ["particle dissolve", "motion blur"],
                        "timing": "fast entrance",
                        "energy": 0.8,
                        "emotion": "dramatic",
                        "style": "cinematic",
                    }},
                }]
            },
            "rules": [
                "Return exactly one DirectorPlanPatch JSON object. A single ```json fenced object is also accepted; no explanatory text or DirectorPlan.",
                "scene_id must be an exact supplied asset_id, never Scene01, scene_001, or an index.",
                "Only include fields the user explicitly asked to change; omit all other changes fields.",
                "For an entrance or visual motion request, set changes.creative_intent. It describes visuals, never a Remotion component or effect ID.",
                "For a duration request, set changes.duration_frames only. For a visual transition request, set changes.transition_intent on the outgoing scene. Describe it naturally; never name an effect type or component.",
                "Keep static image motion policy unchanged. Do not write TSX, React, CSS, ffmpeg, crop, cover, scaleX, or scaleY.",
                "Do not output transition.type or TransitionConfig. Preserve internal baseline transitions locally.",
                "You are a film director, not a renderer. Use cinematic language, never component names or VisualEvent types.",
                "Do not invent unsupported effects. Adapt unavailable requests to the closest supported visual language without rejecting the request.",
                "Generic cinematic or dramatic wording does not automatically add a special effect.",
                "Stretch language describes an entrance into the next shot; never invent stretch_transition.",
            ],
        },
        ensure_ascii=False,
    )


def merge_director_plan_patch(plan: DirectorPlan, patch: DirectorPlanPatch) -> DirectorPlan:
    """Apply explicit Patch fields without allowing an LLM to rewrite the plan."""
    by_asset = {item.asset_id: item for item in plan.timeline}
    replacements = dict(by_asset)
    for operation in patch.operations:
        current = by_asset[operation.scene_id]
        changes = operation.changes
        update: dict[str, object] = {}
        if "duration_frames" in changes.model_fields_set:
            update["duration_frames"] = changes.duration_frames
        if "transition_intent" in changes.model_fields_set:
            update["transition_intent"] = changes.transition_intent.model_copy(
                update={"scene_id": current.asset_id, "style": changes.transition_intent.style or "cinematic"}
            )
        if "transition" in changes.model_fields_set:
            update["transition"] = changes.transition
        if "timing" in changes.model_fields_set:
            update["timing"] = changes.timing
        if "emotion" in changes.model_fields_set:
            # DirectorPlan names the human-readable scene rationale `reason`.
            update["reason"] = changes.emotion
        if "creative_intent" in changes.model_fields_set:
            # The scene identity is owned by the project, not model output.
            update["creative_intent"] = changes.creative_intent.model_copy(
                update={"scene_id": current.asset_id, "style": changes.creative_intent.style or "cinematic"}
            )
        replacements[current.asset_id] = current.model_copy(update=update)
    return plan.model_copy(update={"timeline": [replacements[item.asset_id] for item in plan.timeline]})


def generate_plan(session: ProjectSession, user_request: str = "", on_progress: ProgressCallback | None = None) -> tuple[ProjectSession, str]:
    if on_progress:
        on_progress("导演助手|正在生成导演方案...")
    session.current_plan = create_director_plan(session.project.images, session.beat_analysis.to_analysis(), session.style)
    session.current_storyboard = plan_to_storyboard(session.current_plan, session.style)
    session.dirty = True
    text = "DirectorPlan 已生成并通过校验。"
    if user_request:
        session, feedback = update_plan(session, user_request, on_progress=on_progress)
        text = f"{text}\n{feedback}"
    return session, text


def update_plan(session: ProjectSession, message: str, on_progress: ProgressCallback | None = None) -> tuple[ProjectSession, str]:
    if session.current_plan is None:
        return generate_plan(session, message, on_progress=on_progress)

    previous = session.current_plan
    provider = get_agent_provider("chat")
    updated = previous
    if provider.model_name == "mock":
        response = "Director LLM 当前不可用，未修改计划。请配置 LLM 后重试。"
    else:
        try:
            log_intent_adaptation(message)
            if on_progress:
                on_progress("导演助手|正在理解创意需求...")
            complete_json = getattr(provider, "complete_json", provider.complete)
            raw = complete_json(_chat_prompt(session, message))
            if on_progress:
                on_progress("导演计划|正在解析导演修改...")
            logger.debug("Director Chat raw response: %s", _sanitize_response_for_log(raw))
            patch = validate_director_plan_patch_json(raw, [asset.id for asset in session.project.images])
            updated = merge_director_plan_patch(previous, patch)
            response = f"已应用 {len(patch.operations)} 个导演修改。"
        except ValueError as exc:
            response = f"导演修改未应用：{exc}"
        except Exception:
            response = "Director LLM 请求失败，未修改计划。请检查模型配置后重试。"

    session.current_plan = updated
    if on_progress:
        on_progress("导演计划|正在更新镜头方案...")
    session.current_storyboard = plan_to_storyboard(updated, session.style)
    session.dirty = updated != previous
    session.conversation_history.extend([
        {"role": "user", "content": message},
        {"role": "assistant", "content": response},
    ])
    session.conversation_history = session.conversation_history[-20:]
    if updated != previous:
        session.save()
    return session, response


def _sanitize_response_for_log(raw: str, limit: int = 1000) -> str:
    return _SECRET.sub("[REDACTED]", raw)[:limit]


def format_plan(session: ProjectSession, as_json: bool = False) -> str:
    if session.current_plan is None:
        return "当前还没有 DirectorPlan。输入 plan 生成初版方案。"
    if as_json:
        return session.current_plan.model_dump_json(indent=2)
    lines: list[str] = []
    for index, item in enumerate(session.current_plan.timeline, 1):
        animation = item.creative_intent.description if item.creative_intent else "none"
        creative_transition = item.transition_intent.description if item.transition_intent else "none"
        lines.extend([
            f"Scene {index:02d}",
            f"Asset: {item.asset_id}",
            f"Duration: {item.duration_frames} frames / {item.duration_frames / session.fps:.1f}s",
            f"Animation Design: {animation}",
            f"Transition: {item.transition.type.value} / {item.transition.duration_frames}f (baseline)",
            f"Creative Transition: {creative_transition}",
            f"Emotion: {item.reason}",
            "",
        ])
    return "\n".join(lines).rstrip()


@dataclass
class DirectorSession:
    """Deprecated lightweight API retained only for import compatibility."""

    images: list[dict]
    beat_analysis: object
    style: str = "cinematic"
    current_plan: DirectorPlan | None = None
    conversation_history: list[dict[str, str]] = field(default_factory=list)


def handle_message(session: DirectorSession, message: str) -> tuple[DirectorSession, str]:
    """The interactive workspace requires ProjectSession and an LLM provider."""
    response = "DirectorSession 不支持直接修改；请使用 ProjectSession Director Workspace。"
    session.conversation_history.extend([{"role": "user", "content": message}, {"role": "assistant", "content": response}])
    session.conversation_history = session.conversation_history[-20:]
    return session, response
