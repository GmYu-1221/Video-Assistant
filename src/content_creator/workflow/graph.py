from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from content_creator.agents.animation_agent import animation_node
from content_creator.agents.content_agents import copy_fitting_node, director_node, director_review_node, editorial_node
from content_creator.schemas import CopyFitDecision, SceneSplitTarget, SourceResults
from content_creator.services.source_pipeline import process_source
from content_creator.services.timing import (
    PresentationCapacityError, build_reading_load_report, compile_presentation_plan,
)

from .state import VideoState


def source_node(state: VideoState) -> dict:
    project = state["project"]
    results = []
    with ThreadPoolExecutor(max_workers=len(project.urls), thread_name_prefix="source") as executor:
        futures = {
            executor.submit(
                process_source, source_id=f"source-{index:03d}", url=url,
                project_dir=project.project_dir,
                imported_html=project.imported_html.get(f"source-{index:03d}"),
            ): index
            for index, url in enumerate(project.urls, start=1)
        }
        for future in as_completed(futures):
            results.append((futures[future], future.result()))
    source_results = SourceResults(sources=[result for _, result in sorted(results)])
    path = Path(project.project_dir) / "source_results.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(source_results.model_dump_json(indent=2), encoding="utf-8")
    temporary.replace(path)
    return {"source_results": source_results}


def _after_director_review(state: VideoState) -> str:
    decision = state["copy_fit_decision"]
    if decision.status == "accepted":
        return "animation_agent"
    if decision.status == "split_scene":
        return _split_route(state)
    if state.get("revision_count", 0) <= state["project"].max_copy_revision:
        return "copy_fitting_agent"
    return "copy_revision_failed"


def _split_route(state: VideoState) -> str:
    if len(state["director_plan"].scenes) >= 12:
        return "scene_split_failed"
    if state.get("scene_split_count", 0) <= state["project"].max_scene_split:
        return "director_agent"
    return "scene_split_failed"


def presentation_node(state: VideoState) -> dict:
    project_dir = Path(state["project"].project_dir)
    revision = state.get("revision_count", 0)
    split_count = state.get("scene_split_count", 0)
    suffix = f"revision-{revision:03d}_split-{split_count:03d}"
    try:
        plan = compile_presentation_plan(state["viral_copy_plan"], state["timing_plan"])
    except PresentationCapacityError as exc:
        decision = CopyFitDecision(
            status="split_scene",
            feedback=str(exc),
            split_targets=[SceneSplitTarget(
                scene_id=exc.scene_id, reason=str(exc),
                narrative_nodes=["当前场景的主要叙事节点", "超过当前场景最短可见时间容量的内容页"],
            )],
        )
        path = project_dir / "presentation_validation.json"
        _atomic_text(path, json.dumps({
            "status": "scene_split_required", "error": str(exc),
            "required_frames": exc.required_frames, "available_frames": exc.available_frames,
        }, ensure_ascii=False, indent=2))
        _atomic_text(project_dir / f"presentation_validation_{suffix}.json", path.read_text(encoding="utf-8"))
        return {
            "copy_fit_decision": decision, "scene_split_request": decision,
            "scene_split_count": state.get("scene_split_count", 0) + 1,
        }
    path = project_dir / "presentation_plan.json"
    _atomic_text(path, plan.model_dump_json(indent=2))
    _atomic_text(project_dir / f"presentation_plan_{suffix}.json", plan.model_dump_json(indent=2))
    validation = json.dumps({
        "status": "passed", "scene_count": len(plan.scenes),
        "page_count": sum(len(scene.pages) for scene in plan.scenes),
        "duration_frames": plan.duration_frames,
    }, ensure_ascii=False, indent=2)
    _atomic_text(project_dir / "presentation_validation.json", validation)
    _atomic_text(project_dir / f"presentation_validation_{suffix}.json", validation)
    return {"presentation_plan": plan, "scene_split_request": None}


def _after_presentation(state: VideoState) -> str:
    return _split_route(state) if state.get("scene_split_request") else "director_review"


def _copy_revision_failed(state: VideoState) -> dict:
    decision = state["copy_fit_decision"]
    report = build_reading_load_report(
        state["viral_copy_plan"], state["timing_plan"], state.get("presentation_plan"),
    )
    raise RuntimeError(
        f"Copy fitting exceeded {state['project'].max_copy_revision} revisions; "
        f"final_feedback={decision.feedback!r}; "
        f"page_targets={[target.model_dump(mode='json') for target in decision.page_targets]!r}; "
        f"reading_load_report={report!r}"
    )


def _scene_split_failed(state: VideoState) -> dict:
    decision = state["scene_split_request"] or state["copy_fit_decision"]
    raise RuntimeError(
        f"Director scene split exceeded {state['project'].max_scene_split} upgrade; "
        f"feedback={decision.feedback!r}; "
        f"split_targets={[target.model_dump(mode='json') for target in decision.split_targets]!r}"
    )


def _atomic_text(path: Path, value: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def build_graph():
    graph = StateGraph(VideoState)
    graph.add_node("source_agent", source_node)
    graph.add_node("editorial_agent", editorial_node)
    graph.add_node("copy_fitting_agent", copy_fitting_node)
    graph.add_node("director_agent", director_node)
    graph.add_node("director_review", director_review_node)
    graph.add_node("presentation_compiler", presentation_node)
    graph.add_node("animation_agent", animation_node)
    graph.add_node("copy_revision_failed", _copy_revision_failed)
    graph.add_node("scene_split_failed", _scene_split_failed)
    graph.add_edge(START, "source_agent")
    graph.add_edge("source_agent", "editorial_agent")
    graph.add_edge("editorial_agent", "director_agent")
    graph.add_edge("director_agent", "copy_fitting_agent")
    graph.add_edge("copy_fitting_agent", "presentation_compiler")
    graph.add_conditional_edges("presentation_compiler", _after_presentation, {
        "director_review": "director_review", "director_agent": "director_agent",
        "scene_split_failed": "scene_split_failed",
    })
    graph.add_conditional_edges("director_review", _after_director_review, {
        "copy_fitting_agent": "copy_fitting_agent",
        "animation_agent": "animation_agent",
        "copy_revision_failed": "copy_revision_failed",
        "director_agent": "director_agent",
        "scene_split_failed": "scene_split_failed",
    })
    graph.add_edge("animation_agent", END)
    return graph.compile()
