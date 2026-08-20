from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from content_creator.agents.animation_agent import animation_node
from content_creator.agents.content_agents import copy_fitting_node, director_node, director_review_node, editorial_node
from content_creator.schemas import SourceResults
from content_creator.services.source_pipeline import process_source

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
    if state["copy_fit_decision"].status == "accepted":
        return "animation_agent"
    if state.get("revision_count", 0) <= state["project"].max_copy_revision:
        return "copy_fitting_agent"
    return "copy_revision_failed"


def _copy_revision_failed(state: VideoState) -> dict:
    raise RuntimeError(f"Copy fitting exceeded {state['project'].max_copy_revision} revisions")


def build_graph():
    graph = StateGraph(VideoState)
    graph.add_node("source_agent", source_node)
    graph.add_node("editorial_agent", editorial_node)
    graph.add_node("copy_fitting_agent", copy_fitting_node)
    graph.add_node("director_agent", director_node)
    graph.add_node("director_review", director_review_node)
    graph.add_node("animation_agent", animation_node)
    graph.add_node("copy_revision_failed", _copy_revision_failed)
    graph.add_edge(START, "source_agent")
    graph.add_edge("source_agent", "editorial_agent")
    graph.add_edge("editorial_agent", "director_agent")
    graph.add_edge("director_agent", "copy_fitting_agent")
    graph.add_edge("copy_fitting_agent", "director_review")
    graph.add_conditional_edges("director_review", _after_director_review, {
        "copy_fitting_agent": "copy_fitting_agent",
        "animation_agent": "animation_agent",
        "copy_revision_failed": "copy_revision_failed",
    })
    graph.add_edge("animation_agent", END)
    return graph.compile()
