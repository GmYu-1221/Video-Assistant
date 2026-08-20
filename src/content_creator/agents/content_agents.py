"""Editorial, copy-fitting and implementation-neutral direction agents."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from content_creator.agents.viral_writer import load_viral_writer_skill
from content_creator.schemas import (
    CopyFitDecision, CopyScene, CopyFitReviewDecision, DirectorDecision, DirectorPlan,
    DirectorScene, EditorialBeat, EditorialDecision, EditorialPlan, SourceReference,
    ViralCopyDecision, ViralCopyPlan,
)
from content_creator.services.llm.router import require_agent_provider
from content_creator.services.structured_agent import StructuredAgentRunner, issue
from content_creator.services.timing import compile_timing_plan


def _source_payload(state: dict) -> list[dict]:
    return [source.model_dump(mode="json") for source in state["source_results"].sources]


def _reference_issues(state: dict, located_references) -> list:
    limits = {
        source.source_id: len([line for line in source.body.splitlines() if line.strip()])
        for source in state["source_results"].sources
    }
    issues = []
    for path, reference in located_references:
        if reference.source_id not in limits:
            issues.append(issue(path + ("source_id",), "unknown_source_id", f"source_id {reference.source_id!r} is not present in input"))
        elif reference.paragraph_index >= limits[reference.source_id]:
            issues.append(issue(path + ("paragraph_index",), "unknown_paragraph_index", f"paragraph_index {reference.paragraph_index} is not present in {reference.source_id}"))
    return issues


def editorial_node(state: dict) -> dict:
    provider = require_agent_provider("editorial")
    prompt = json.dumps({
        "role": "Editorial Agent",
        "question": "这些来源最终应该讲什么？",
        "requirements": [
            "融合所有来源并去除重复信息", "决定主观点和优先级", "建立短视频叙事结构",
            "每个事实点必须引用 source_id 和 paragraph_index", "不要描述动画、网页或代码",
        ],
        "sources": _source_payload(state),
    }, ensure_ascii=False)
    decision = StructuredAgentRunner().run(
        provider=provider, contract_name="editorial", prompt=json.loads(prompt), schema=EditorialDecision,
        artifact_dir=state["project"].project_dir,
        semantic_validator=lambda value: _reference_issues(state, [
            (("beats", beat_index, "source_references", ref_index), ref)
            for beat_index, beat in enumerate(value.beats)
            for ref_index, ref in enumerate(beat.source_references)
        ]),
    )
    plan = EditorialPlan(
        thesis=decision.thesis, audience=decision.audience, narrative=decision.narrative,
        title_direction=decision.title_direction, mood=decision.mood, topics=decision.topics,
        beats=[EditorialBeat(
            id=f"beat-{index:03d}", purpose=beat.purpose, point=beat.point, priority=beat.priority,
            source_references=[SourceReference.model_validate(ref.model_dump()) for ref in beat.source_references],
        ) for index, beat in enumerate(decision.beats, 1)],
    )
    _persist(state, "editorial_plan.json", plan)
    return {"editorial_plan": plan}


def copy_fitting_node(state: dict) -> dict:
    provider = require_agent_provider("copy_fitting")
    revision = state.get("revision_count", 0)
    director = state["director_plan"]
    timing = state["timing_plan"]
    prompt = json.dumps({
        "role": "Copy Fitting Agent",
        "question": "如何在导演已经锁定的每幕时间和字数预算内完成文案？",
        "locked_target": {
            "duration_seconds": director.duration_seconds,
            "duration_frames": timing.duration_frames,
            "fps": timing.fps,
            "scenes": [
                timing_scene.model_dump(mode="json") | {
                    "duration_seconds": (timing_scene.end_frame - timing_scene.start_frame) / timing.fps
                }
                for timing_scene in timing.scenes
            ],
        },
        "requirements": [
            "只输出 ViralCopyPlan，不输出或修改 timing、总时长、FPS、scene 划分或顺序",
            "输出简体中文短视频文案", "每幕文案必须适配对应 text_budget",
            "scene_id 和顺序必须与导演场景完全一致", "每幕保留来源引用", "不要输出动画实现",
        ],
        "revision_count": revision,
        "director_revision_feedback": state.get("copy_fit_decision").model_dump(mode="json") if state.get("copy_fit_decision") else None,
        "editorial_plan": state["editorial_plan"].model_dump(mode="json"),
        "director_plan": director.model_dump(mode="json"),
        "sources": _source_payload(state),
        "viral_writer_skill": load_viral_writer_skill(),
    }, ensure_ascii=False)
    def validate_copy(value: ViralCopyDecision):
        director_ids = [scene.scene_id for scene in director.scenes]
        result = []
        if len(value.scenes) != len(director_ids):
            result.append(issue(("scenes",), "scene_count_mismatch", f"expected {len(director_ids)} scenes, got {len(value.scenes)}"))
        for index, scene in enumerate(value.scenes):
            if index >= len(director_ids) or scene.scene_id != director_ids[index]:
                result.append(issue(("scenes", index, "scene_id"), "scene_id_order_mismatch", f"must equal Director scene at index {index}"))
        result.extend(_reference_issues(state, [
            (("scenes", scene_index, "source_references", ref_index), ref)
            for scene_index, scene in enumerate(value.scenes)
            for ref_index, ref in enumerate(scene.source_references)
        ]))
        return result

    try:
        decision = StructuredAgentRunner().run(
            provider=provider, contract_name="copy_fitting", prompt=json.loads(prompt), schema=ViralCopyDecision,
            artifact_dir=state["project"].project_dir, semantic_validator=validate_copy,
        )
    finally:
        _mirror_contract_files(state, "copy_fitting")
    plan = ViralCopyPlan(
        final_title=decision.final_title, hook=decision.hook, closing=decision.closing,
        scenes=[CopyScene(
            scene_id=scene.scene_id, title=scene.title, body=scene.body, emphasis=scene.emphasis,
            source_references=[SourceReference.model_validate(ref.model_dump()) for ref in scene.source_references],
        ) for scene in decision.scenes],
    )
    copy_ids = [scene.scene_id for scene in plan.scenes]
    _persist(state, "viral_copy_plan.json", plan)
    return {"viral_copy_plan": plan}


def director_node(state: dict) -> dict:
    provider = require_agent_provider("director")
    prompt = json.dumps({
        "role": "Director Agent",
        "question": "整条视频应该怎么呈现？",
        "hard_boundary": "只输出实现无关的视觉方案。禁止任何框架、组件、模板、registry、动画 API、CSS 代码或 DOM 结构。",
        "duration_decision": [
            "duration_seconds 必须是 15 到 90 的整数",
            "根据 EditorialPlan 的叙事信息量、核心 beat 数量、SourceResults 实际可用素材数量和整体节奏决定总时长",
            "只输出 duration_seconds；禁止输出 duration_frames，帧数由 Python 使用 duration_seconds * project.fps 计算",
            "为每幕给出正数 duration_weight，表达相对节奏，不计算具体帧区间",
        ],
        "allowed": [
            "总秒数和场景", "图片顺序和使用意图", "入场、镜头和转场意图",
            "视觉密度、信息层级、标题/媒体/正文区域意图", "安全区、背景氛围、字体层级、节奏",
        ],
        "project": state["project"].model_dump(mode="json"),
        "source_results": _source_payload(state),
        "editorial_plan": state["editorial_plan"].model_dump(mode="json"),
    }, ensure_ascii=False)
    project = state["project"]
    material_ids = {item.id for source in state["source_results"].sources for item in source.materials}
    def validate_director(value: DirectorDecision):
        result = []
        for scene_index, scene in enumerate(value.scenes):
            seen = set()
            for material_index, material_id in enumerate(scene.material_ids):
                path = ("scenes", scene_index, "material_ids", material_index)
                if material_id not in material_ids:
                    result.append(issue(path, "unknown_material_id", f"material_id {material_id!r} is not present in input"))
                elif material_id in seen:
                    result.append(issue(path, "duplicate_material_id", f"material_id {material_id!r} is duplicated in this scene"))
                seen.add(material_id)
        implementation_pattern = re.compile(r"gsap\.|display\s*:|grid-template|clip-path|<\w+|document\.|window\.", re.I)
        for field_name in ("safe_area", "background_atmosphere", "typography_hierarchy", "alignment_tendency", "rhythm"):
            if implementation_pattern.search(getattr(value, field_name)):
                result.append(issue((field_name,), "implementation_specific", "Director must return implementation-neutral intent"))
        for scene_index, scene in enumerate(value.scenes):
            for field_name in ("image_intent", "camera_intent", "transition_intent", "information_hierarchy"):
                if implementation_pattern.search(getattr(scene, field_name)):
                    result.append(issue(("scenes", scene_index, field_name), "implementation_specific", "Director must return implementation-neutral intent"))
        return result

    decision = StructuredAgentRunner().run(
        provider=provider, contract_name="director", prompt=json.loads(prompt), schema=DirectorDecision,
        artifact_dir=project.project_dir, semantic_validator=validate_director,
    )
    plan = DirectorPlan(
        width=project.width, height=project.height, fps=project.fps,
        duration_seconds=decision.duration_seconds, duration_reason=decision.duration_reason,
        safe_area=decision.safe_area, background_atmosphere=decision.background_atmosphere,
        typography_hierarchy=decision.typography_hierarchy, alignment_tendency=decision.alignment_tendency,
        rhythm=decision.rhythm,
        scenes=[DirectorScene(
            scene_id=f"scene-{index:03d}", material_ids=scene.material_ids,
            duration_weight=scene.duration_weight, image_intent=scene.image_intent,
            camera_intent=scene.camera_intent, transition_intent=scene.transition_intent,
            information_hierarchy=scene.information_hierarchy, visual_density=scene.visual_density,
        ) for index, scene in enumerate(decision.scenes, 1)],
    )
    timing = compile_timing_plan(
        total_frames=plan.duration_seconds * project.fps,
        fps=project.fps,
        scenes=plan.scenes,
    )
    _persist(state, "director_plan.json", plan)
    _persist(state, "timing_plan.json", timing)
    return {"director_plan": plan, "timing_plan": timing}


def director_review_node(state: dict) -> dict:
    """Review copy capacity without reopening any locked timing decision."""
    provider = require_agent_provider("director")
    prompt = json.dumps({
        "role": "Director Review",
        "question": "文案是否能在锁定的每幕时间预算内清晰呈现？",
        "hard_boundary": "只能接受文案或要求压缩。禁止修改总时长、FPS、scene、duration_weight 或任何帧区间。",
        "requirements": [
            "status 只能是 accepted 或 revise",
            "revise 时用 feedback 和 targets 给出明确压缩目标",
            "targets 中的 scene_id 只能引用输入 ID，max_chars 不得超过该幕 text_budget",
            "accepted 时 targets 必须是空数组",
        ],
        "director_plan": state["director_plan"].model_dump(mode="json"),
        "timing_plan": state["timing_plan"].model_dump(mode="json"),
        "viral_copy_plan": state["viral_copy_plan"].model_dump(mode="json"),
    }, ensure_ascii=False)
    budgets = {scene.scene_id: scene.text_budget for scene in state["timing_plan"].scenes}
    def validate_review(value: CopyFitReviewDecision):
        result = []
        seen = set()
        if value.status == "accepted" and value.targets:
            result.append(issue(("targets",), "accepted_has_targets", "accepted review must use an empty targets array", related_paths=(("status",),)))
        if value.status == "revise" and not value.feedback:
            result.append(issue(("feedback",), "revision_feedback_missing", "revise review requires feedback"))
        for index, target in enumerate(value.targets):
            if target.scene_id not in budgets:
                result.append(issue(("targets", index, "scene_id"), "unknown_scene_id", f"scene_id {target.scene_id!r} is not present in input"))
            elif target.max_chars > budgets[target.scene_id]:
                result.append(issue(("targets", index, "max_chars"), "text_budget_exceeded", f"max_chars exceeds locked budget {budgets[target.scene_id]}"))
            if target.scene_id in seen:
                result.append(issue(("targets", index, "scene_id"), "duplicate_scene_id", "scene target is duplicated"))
            seen.add(target.scene_id)
        return result

    reviewed = StructuredAgentRunner().run(
        provider=provider, contract_name="director_review", prompt=json.loads(prompt), schema=CopyFitReviewDecision,
        artifact_dir=state["project"].project_dir, semantic_validator=validate_review,
    )
    decision = CopyFitDecision(
        status=reviewed.status, feedback=reviewed.feedback,
        scene_targets={target.scene_id: target.max_chars for target in reviewed.targets},
    )
    _persist(state, "copy_fit_decision.json", decision)
    result = {"copy_fit_decision": decision}
    if decision.status == "revise":
        result["revision_count"] = state.get("revision_count", 0) + 1
    return result


def _persist(state: dict, name: str, model) -> None:
    path = Path(state["project"].project_dir) / name
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(model.model_dump_json(indent=2), encoding="utf-8")
    temporary.replace(path)


def _mirror_contract_files(state: dict, contract_name: str) -> None:
    run_dir = Path(state["project"].project_dir) / "agent_runs" / contract_name
    response = run_dir / ("attempt-2.txt" if (run_dir / "attempt-2.txt").is_file() else "attempt-1.txt")
    if response.is_file():
        shutil.copyfile(response, Path(state["project"].project_dir) / f"{contract_name}_response.txt")
    validation = run_dir / "validation.json"
    if validation.is_file():
        shutil.copyfile(validation, Path(state["project"].project_dir) / f"{contract_name}_validation.json")
