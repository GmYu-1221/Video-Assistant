"""Multimodal HTML/CSS/GSAP implementation agent."""
from __future__ import annotations

import json
from pathlib import Path

from content_creator.schemas import AnimationArtifact
from content_creator.services.html_validator import (
    AnimationHTMLValidationError, extract_complete_html, validate_animation_html,
    validate_animation_html_repair_scope,
)
from content_creator.services.llm.router import require_agent_provider


def animation_node(state: dict) -> dict:
    provider = require_agent_provider("animation")
    project = state["project"]
    project_dir = Path(project.project_dir)
    materials = [material for source in state["source_results"].sources for material in source.materials]
    image_paths = [str(project_dir / material.path) for material in materials]
    fonts = sorted(
        path.relative_to(project_dir).as_posix()
        for path in (project_dir / "runtime" / "fonts").rglob("*")
        if path.suffix.lower() in {".ttf", ".otf", ".woff", ".woff2"}
    )
    prompt_payload = {
        "role": "Animation Agent",
        "question": "如何用 HTML、CSS、SVG 和 GSAP 把导演方案实现为逐帧确定性动画？",
        "inputs": {
            "source_results": state["source_results"].model_dump(mode="json"),
            "editorial_plan": state["editorial_plan"].model_dump(mode="json"),
            "viral_copy_plan": state["viral_copy_plan"].model_dump(mode="json"),
            "timing_plan": state["timing_plan"].model_dump(mode="json"),
            "presentation_plan": state["presentation_plan"].model_dump(mode="json"),
            "director_plan": state["director_plan"].model_dump(mode="json"),
            "materials": [item.model_dump(mode="json") for item in materials],
            "fonts": fonts,
        },
        "runtime_contract": {
            "document": "返回唯一完整 <!doctype html> 文档，不要解释或 Markdown",
            "gsap": "只从 runtime/gsap.min.js 加载 GSAP 3.15.0 core",
            "timeline": "必须直接声明 const masterTimeline = gsap.timeline({paused: true}); 所有主要动画必须加入该 timeline。变量名必须逐字为 masterTimeline，禁止使用 tl/timeline 等别名后再赋给 window.masterTimeline",
            "meta": {"width": project.width, "height": project.height, "fps": project.fps, "durationFrames": state["timing_plan"].duration_frames},
            "globals": ["window.renderFrame", "window.__ANIMATION_READY__", "window.__ANIMATION_META__"],
            "render_frame": "必须逐字采用以下结构（允许调整空格和换行，不得改用 seek/totalTime/其他 timeline）：\nwindow.renderFrame = async function(frame) {\n  const fps = window.__ANIMATION_META__.fps;\n  const time = frame / fps;\n  masterTimeline.time(time, false);\n  await document.fonts.ready;\n};",
            "ready": "默认 false；本地图片和字体加载完成后设置 true",
        },
        "visual_principles": [
            "竖屏短视频，简约，图片是视觉主体", "清楚的标题→图片→正文层级",
            "不要假 UI、Dashboard、卡片墙或复杂杂志排版", "图片切换必须由 paused GSAP timeline 驱动",
            "严格按 presentation_plan 的 page 帧边界切换对应 material_id 和 texts；不得自行合并、重排或重新分页",
            "逐字段遵守 page.field_budgets 的字号和最大行数；缺少 text item 的字段不得制造占位视觉",
            "base_reading_units_per_second 只是已编译预算的启发式基准，不代表配音或绝对人类阅读速度",
        ],
        "forbidden": [
            "CDN和远程资源", "fetch/XHR/WebSocket/EventSource", "iframe/object/embed", "dynamic import/eval/Function",
            "CSS animation或transition计时", "setTimeout/setInterval/requestAnimationFrame", "真实时钟、Math.random、自动播放 timeline",
            "masterTimeline 的变量别名和 window.masterTimeline = alias",
        ],
    }
    prompt_path = project_dir / "animation_prompt.json"
    _atomic_text(prompt_path, json.dumps(prompt_payload, ensure_ascii=False, indent=2))
    attempts: list[dict] = []

    def invoke(prompt: str, attempt: int) -> str:
        try:
            response = provider.complete_multimodal_text(prompt, image_paths)
        except Exception as exc:
            attempts.append({
                "attempt": attempt, "status": "invocation_failed",
                "error": f"{type(exc).__name__}: {exc}",
            })
            _write_validation(project_dir, provider.model_name, "invocation_failed", attempts)
            raise
        _atomic_text(project_dir / f"animation_response_attempt-{attempt}.txt", response)
        _atomic_text(project_dir / "animation_response.txt", response)
        return response

    def validate(raw_html: str) -> str:
        document = extract_complete_html(raw_html)
        validate_animation_html(
            document, project_dir, width=project.width, height=project.height, fps=project.fps,
            duration_frames=state["timing_plan"].duration_frames,
        )
        return document

    raw = invoke(json.dumps(prompt_payload, ensure_ascii=False), 1)
    try:
        html = validate(raw)
        attempts.append({"attempt": 1, "status": "passed", "error": None})
        validation_status = "passed"
        repair_count = 0
    except AnimationHTMLValidationError as first_error:
        attempts.append({"attempt": 1, "status": "failed", "error": str(first_error)})
        original_html = _best_effort_html(raw)
        repair_payload = {
            "role": "Animation HTML Contract Repair",
            "task": "只修复当前 HTML Contract error，并返回唯一完整 <!doctype html> 文档，不要解释或 Markdown。",
            "contract_error": str(first_error),
            "previous_html": raw,
            "runtime_contract": prompt_payload["runtime_contract"],
            "repair_scope": {
                "allowed": "修改所有与当前 contract_error 直接相关的代码声明和代码引用。若修复 masterTimeline，可统一重命名声明及其全部代码引用，并删除 alias bridge。",
                "immutable": [
                    "动画参数和 GSAP properties", "动画 duration、position 和所有时间点",
                    "DOM 结构", "CSS 视觉样式", "素材路径和素材选择", "可见文案", "布局意图",
                ],
                "attempt_limit": 1,
            },
        }
        repair_prompt = json.dumps(repair_payload, ensure_ascii=False)
        _atomic_text(project_dir / "animation_repair_prompt.json", json.dumps(repair_payload, ensure_ascii=False, indent=2))
        repaired_raw = invoke(repair_prompt, 2)
        try:
            repaired_html = validate(repaired_raw)
            validate_animation_html_repair_scope(original_html, repaired_html, str(first_error))
        except AnimationHTMLValidationError as second_error:
            attempts.append({"attempt": 2, "status": "failed", "error": str(second_error)})
            _write_validation(project_dir, provider.model_name, "failed", attempts)
            raise
        attempts.append({"attempt": 2, "status": "passed", "error": None})
        html = repaired_html
        validation_status = "passed_after_repair"
        repair_count = 1

    _write_validation(project_dir, provider.model_name, validation_status, attempts)
    html_path = project_dir / "animation.html"
    _atomic_text(html_path, html)
    artifact = AnimationArtifact(
        html_path=str(html_path), model=provider.model_name,
        width=project.width, height=project.height, fps=project.fps,
        duration_frames=state["timing_plan"].duration_frames,
        materials=[item.path for item in materials], fonts=fonts,
        prompt_path=str(prompt_path), artifact_metadata={
            "revision_count": state.get("revision_count", 0),
            "scene_split_count": state.get("scene_split_count", 0),
            "contract_repair_count": repair_count,
        },
    )
    _atomic_text(project_dir / "animation_artifact.json", artifact.model_dump_json(indent=2))
    return {"animation_artifact": artifact}


def _atomic_text(path: Path, value: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def _best_effort_html(raw: str) -> str:
    try:
        return extract_complete_html(raw)
    except AnimationHTMLValidationError:
        return raw


def _write_validation(project_dir: Path, model: str, status: str, attempts: list[dict]) -> None:
    payload = {"status": status, "model": model, "attempts": attempts}
    if status in {"failed", "invocation_failed"} and attempts:
        payload["error"] = attempts[-1]["error"]
    _atomic_text(
        project_dir / "animation_validation.json",
        json.dumps(payload, ensure_ascii=False, indent=2),
    )
