from __future__ import annotations
import json
from pathlib import Path

from content_creator.schemas import LayoutIssue, VisualCriticResult
from content_creator.services.llm.router import get_agent_provider


def critique_scene(*, rendered_ok: bool, hard_issues: list[LayoutIssue], preview_paths: list[str] | None = None, scene_purpose: str = "") -> VisualCriticResult:
    # Deterministic baseline prevents unavailable multimodal infrastructure from
    # blocking rendering. QA still records that no model judgement was used.
    critical = any(issue.severity == "critical" for issue in hard_issues)
    baseline_ok = rendered_ok and not critical
    unavailable = VisualCriticResult(passed=False, quality_score=0, issues=[], mode="critic_unavailable")
    provider = get_agent_provider("visual_critic")
    paths = [path for path in preview_paths or [] if Path(path).is_file()]
    if provider.model_name == "mock" or not paths or not baseline_ok:
        return unavailable
    prompt = json.dumps({"task": "Judge a single video scene preview. Return JSON only: pass, quality_score 0..1, issues[]. Inspect readability, subject occlusion, whitespace, hierarchy, awkward line breaks, and PPT-like composition.", "scene_purpose": scene_purpose, "output": {"pass": True, "quality_score": .8, "issues": [{"code": "short_code", "severity": "info|warning|error|critical", "block_id": "optional", "message": "short", "repair_hint": "short"}]}}, ensure_ascii=False)
    try:
        raw = provider.complete_multimodal(prompt, paths)
        parsed = VisualCriticResult.model_validate(json.loads(raw))
        # A critic cannot waive deterministic correctness.
        return parsed.model_copy(update={"passed": parsed.passed and baseline_ok, "mode": "multimodal"})
    except Exception as exc:
        return unavailable.model_copy(update={"error": f"{type(exc).__name__}: {exc}"})
