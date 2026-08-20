"""Multimodal HTML/CSS/GSAP implementation agent."""
from __future__ import annotations

import json
from pathlib import Path

from content_creator.schemas import AnimationArtifact
from content_creator.services.html_validator import AnimationHTMLValidationError, extract_complete_html, validate_animation_html
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
            "director_plan": state["director_plan"].model_dump(mode="json"),
            "materials": [item.model_dump(mode="json") for item in materials],
            "fonts": fonts,
        },
        "runtime_contract": {
            "document": "返回唯一完整 <!doctype html> 文档，不要解释或 Markdown",
            "gsap": "只从 runtime/gsap.min.js 加载 GSAP 3.15.0 core",
            "timeline": "const masterTimeline = gsap.timeline({paused: true}); 所有主要动画必须加入该 timeline",
            "meta": {"width": project.width, "height": project.height, "fps": project.fps, "durationFrames": state["timing_plan"].duration_frames},
            "globals": ["window.renderFrame", "window.__ANIMATION_READY__", "window.__ANIMATION_META__"],
            "render_frame": "必须逐字采用以下结构（允许调整空格和换行，不得改用 seek/totalTime/其他 timeline）：\nwindow.renderFrame = async function(frame) {\n  const fps = window.__ANIMATION_META__.fps;\n  const time = frame / fps;\n  masterTimeline.time(time, false);\n  await document.fonts.ready;\n};",
            "ready": "默认 false；本地图片和字体加载完成后设置 true",
        },
        "visual_principles": [
            "竖屏短视频，简约，图片是视觉主体", "清楚的标题→图片→正文层级",
            "不要假 UI、Dashboard、卡片墙或复杂杂志排版", "图片切换必须由 paused GSAP timeline 驱动",
        ],
        "forbidden": [
            "CDN和远程资源", "fetch/XHR/WebSocket/EventSource", "iframe/object/embed", "dynamic import/eval/Function",
            "CSS animation或transition计时", "setTimeout/setInterval/requestAnimationFrame", "真实时钟、Math.random、自动播放 timeline",
        ],
    }
    prompt_path = project_dir / "animation_prompt.json"
    _atomic_text(prompt_path, json.dumps(prompt_payload, ensure_ascii=False, indent=2))
    raw = provider.complete_multimodal_text(json.dumps(prompt_payload, ensure_ascii=False), image_paths)
    _atomic_text(project_dir / "animation_response.txt", raw)
    try:
        html = extract_complete_html(raw)
        validate_animation_html(
            html, project_dir, width=project.width, height=project.height, fps=project.fps,
            duration_frames=state["timing_plan"].duration_frames,
        )
    except AnimationHTMLValidationError as exc:
        _atomic_text(
            project_dir / "animation_validation.json",
            json.dumps({"status": "failed", "model": provider.model_name, "error": str(exc)}, ensure_ascii=False, indent=2),
        )
        raise
    _atomic_text(
        project_dir / "animation_validation.json",
        json.dumps({"status": "passed", "model": provider.model_name}, ensure_ascii=False, indent=2),
    )
    html_path = project_dir / "animation.html"
    _atomic_text(html_path, html)
    artifact = AnimationArtifact(
        html_path=str(html_path), model=provider.model_name,
        width=project.width, height=project.height, fps=project.fps,
        duration_frames=state["timing_plan"].duration_frames,
        materials=[item.path for item in materials], fonts=fonts,
        prompt_path=str(prompt_path), artifact_metadata={"revision_count": state.get("revision_count", 0)},
    )
    _atomic_text(project_dir / "animation_artifact.json", artifact.model_dump_json(indent=2))
    return {"animation_artifact": artifact}


def _atomic_text(path: Path, value: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)
