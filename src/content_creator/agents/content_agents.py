"""Editorial, copy-fitting and implementation-neutral direction agents."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from content_creator.schemas import (
    CopyFitDecision, CopyFitPageTarget, CopyFitReviewDecision, CopyPage, CopyPageText, CopyScene,
    DirectorDecision, DirectorPlan, DirectorScene, DirectorTextLayout, EditorialBeat, EditorialDecision,
    EditorialPlan, SceneSplitTarget, SourceReference, ViralCopyDecision, ViralCopyPlan,
)
from content_creator.services.llm.router import require_agent_provider
from content_creator.services.structured_agent import StructuredAgentRunner, issue
from content_creator.services.timing import (
    build_reading_load_report, compile_presentation_plan, compile_timing_plan,
    display_width_units, required_display_lines,
)


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


def _copy_page_issues(value: ViralCopyDecision, director, timing, prior_decision: CopyFitDecision | None) -> list:
    result = []
    for scene_index, (scene, director_scene, timing_scene) in enumerate(zip(value.scenes, director.scenes, timing.scenes)):
        allowed_materials = set(director_scene.material_ids)
        budgets = {budget.field: budget for budget in timing_scene.field_budgets}
        used_fields = set()
        for page_index, page in enumerate(scene.pages):
            if page.material_id not in allowed_materials:
                result.append(issue(
                    ("scenes", scene_index, "pages", page_index, "material_id"), "unknown_scene_material_id",
                    f"material_id {page.material_id!r} is not approved for scene {scene.scene_id}",
                ))
            fields = [text.field for text in page.texts]
            for text_index, text in enumerate(page.texts):
                path = ("scenes", scene_index, "pages", page_index, "texts", text_index)
                if fields.count(text.field) > 1:
                    result.append(issue(path + ("field",), "duplicate_page_field", f"field {text.field!r} is duplicated on this page"))
                if text.field not in budgets:
                    result.append(issue(path + ("field",), "unplanned_visible_field", f"field {text.field!r} has no Director text layout"))
                    continue
                used_fields.add(text.field)
                budget = budgets[text.field]
                units = display_width_units(text.text)
                lines = required_display_lines(text.text, budget.max_units_per_line)
                messages = []
                if units > budget.max_total_units:
                    messages.append(f"display_units={units:g} exceeds per-page max_total_units={budget.max_total_units:g}")
                if lines > budget.max_lines:
                    messages.append(f"required_lines={lines} exceeds max_lines={budget.max_lines}")
                if messages:
                    result.append(issue(
                        path + ("text",), "page_text_budget_exceeded",
                        "; ".join(messages) + "; split this text across additional pages before compressing",
                        related_paths=(("scenes", scene_index, "pages", "missing-page"),),
                    ))
                if text.field == "hook" and (scene_index != 0 or page_index != 0):
                    result.append(issue(path + ("field",), "hook_wrong_page", "hook is only allowed on the first page of the first scene"))
                if text.field == "closing" and (
                    scene_index != len(value.scenes) - 1 or page_index != len(scene.pages) - 1
                ):
                    result.append(issue(path + ("field",), "closing_wrong_page", "closing is only allowed on the last page of the last scene"))
        for field in budgets.keys() - used_fields:
            result.append(issue(
                ("scenes", scene_index, "pages", "missing-field", field), "planned_field_missing",
                f"Director configured {field!r}; include it on at least one page",
                related_paths=(("scenes", scene_index, "pages", "missing-page"),),
            ))
    if prior_decision and prior_decision.status == "revise_copy":
        scene_index_by_id = {scene.scene_id: index for index, scene in enumerate(value.scenes)}
        for target in prior_decision.page_targets:
            if target.action != "compress" or target.max_display_units is None:
                continue
            scene_index = scene_index_by_id.get(target.scene_id)
            if scene_index is None or target.page_index >= len(value.scenes[scene_index].pages):
                continue
            page = value.scenes[scene_index].pages[target.page_index]
            matching = next((text for text in page.texts if text.field == target.field), None)
            if matching and display_width_units(matching.text) > target.max_display_units:
                result.append(issue(
                    ("scenes", scene_index, "pages", target.page_index, "texts"), "director_target_not_met",
                    f"field {target.field} exceeds Director target {target.max_display_units:g}",
                ))
    return result


def _copy_manifest(director, timing) -> list[dict]:
    return [{
        "scene_id": scene.scene_id,
        "approved_material_ids": scene.material_ids,
        "page_limit": 12,
        "fields": [{
            "field": budget.field, "max_display_units_per_page": budget.max_total_units,
            "max_lines_per_page": budget.max_lines, "max_units_per_line": budget.max_units_per_line,
            "min_visible_frames_per_page": budget.min_visible_frames,
        } for budget in timing_scene.field_budgets],
        "scene_frames": timing_scene.end_frame - timing_scene.start_frame,
    } for scene, timing_scene in zip(director.scenes, timing.scenes)]


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
    prior_decision = state.get("copy_fit_decision")
    contract_name = f"copy_fitting_revision-{revision:03d}"
    prompt = json.dumps({
        "role": "Copy Fitting Agent",
        "question": "如何把文案分页适配到导演已经锁定的 scene 时间内？",
        "copy_field_manifest": _copy_manifest(director, timing),
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
            "输出简体中文短视频文案；长文案默认拆成多个连续 page，不要求优先压缩",
            "每页只列实际显示的 texts；空字段不要创建 text item，因此不产生预算或阅读负荷",
            "每个 text 必须适配 manifest 对应字段的单页显示单位和行数；超长内容先拆页",
            "Director 配置的每个 field 至少在该 scene 的一页出现一次；未配置 field 禁止出现",
            "每页 material_id 只能来自该 scene approved_material_ids；同一素材允许跨页复用",
            "hook 只在第一 scene 首页；closing 只在最后 scene 末页",
            "base_reading_units_per_second 只是屏幕阅读负荷启发式基准，不代表配音或绝对人类阅读速度",
            "scene_id 和顺序必须与导演场景完全一致", "每页保留来源引用", "不要输出动画实现",
        ],
        "revision_count": revision,
        "director_revision_feedback": prior_decision.model_dump(mode="json") if prior_decision else None,
        "editorial_plan": state["editorial_plan"].model_dump(mode="json"),
        "director_plan": director.model_dump(mode="json"),
        "sources": _source_payload(state),
        "viral_writer_guidance": "保留单一核心观点、事实依据、短句节奏和记忆点；本任务的分页与字段预算优先于长文平台格式。",
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
            (("scenes", scene_index, "pages", page_index, "source_references", ref_index), ref)
            for scene_index, scene in enumerate(value.scenes)
            for page_index, page in enumerate(scene.pages)
            for ref_index, ref in enumerate(page.source_references)
        ]))
        if len(value.scenes) == len(director.scenes):
            result.extend(_copy_page_issues(value, director, timing, prior_decision))
        return result

    try:
        decision = StructuredAgentRunner().run(
            provider=provider, contract_name=contract_name, prompt=json.loads(prompt), schema=ViralCopyDecision,
            artifact_dir=state["project"].project_dir, semantic_validator=validate_copy,
        )
    finally:
        _mirror_contract_files(state, contract_name, "copy_fitting")
    plan = ViralCopyPlan(
        final_title=decision.final_title,
        scenes=[CopyScene(
            scene_id=scene.scene_id,
            pages=[CopyPage(
                page_id=f"{scene.scene_id}-page-{page_index:03d}", material_id=page.material_id,
                texts=[CopyPageText.model_validate(text.model_dump()) for text in page.texts],
                source_references=[SourceReference.model_validate(ref.model_dump()) for ref in page.source_references],
            ) for page_index, page in enumerate(scene.pages, 1)],
        ) for scene in decision.scenes],
    )
    _persist(state, "viral_copy_plan.json", plan)
    _persist(state, f"viral_copy_plan_revision-{revision:03d}.json", plan)
    return {"viral_copy_plan": plan}


def director_node(state: dict) -> dict:
    provider = require_agent_provider("director")
    split_request = state.get("scene_split_request")
    previous_director = state.get("director_plan") if split_request else None
    split_count = state.get("scene_split_count", 0)
    contract_name = f"director_split-{split_count:03d}" if split_request else "director"
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
            "为实际显示的 hook/title/body/emphasis/closing 选择 typography、visibility 和 hierarchy 预设档位",
        ],
        "text_layout_contract": [
            "不要为不显示的空字段创建 text_layout；Copy Fitting 会令没有 layout 的字段保持为空",
            "全局 hook 必须配置在第一幕且只能出现一次；closing 如显示只能配置在最后一幕",
            "只能选择预设档位，禁止计算字号、行数、字符上限、出现帧数或阅读负荷",
            "hierarchy/field coefficient 越高表示文字必须越精炼，因此 Python 计算出的 max_total_units 越少",
        ],
        "scene_split_upgrade": ({
            "task": "只拆分请求指出的过载 scene，并输出一份完整的新 DirectorDecision",
            "request": split_request.model_dump(mode="json"),
            "locked_duration_seconds": previous_director.duration_seconds,
            "requirements": [
                "duration_seconds 必须保持不变", "把每个独立叙事节点放入不同 scene",
                "可重新分配 duration_weight，但不得增加总时长", "其他 scene 的语义和素材意图保持稳定",
            ],
            "previous_director_plan": previous_director.model_dump(mode="json"),
        } if split_request else None),
        "project": state["project"].model_dump(mode="json"),
        "source_results": _source_payload(state),
        "editorial_plan": state["editorial_plan"].model_dump(mode="json"),
    }, ensure_ascii=False)
    project = state["project"]
    material_ids = {item.id for source in state["source_results"].sources for item in source.materials}
    def validate_director(value: DirectorDecision):
        result = []
        if previous_director and value.duration_seconds != previous_director.duration_seconds:
            result.append(issue(
                ("duration_seconds",), "split_changed_duration",
                f"scene split must preserve duration_seconds={previous_director.duration_seconds}",
            ))
        if previous_director and len(value.scenes) <= len(previous_director.scenes):
            result.append(issue(
                ("scenes", "missing-split"), "scene_split_not_applied",
                "scene split upgrade must increase the number of scenes",
            ))
        for scene_index, scene in enumerate(value.scenes):
            seen = set()
            for material_index, material_id in enumerate(scene.material_ids):
                path = ("scenes", scene_index, "material_ids", material_index)
                if material_id not in material_ids:
                    result.append(issue(path, "unknown_material_id", f"material_id {material_id!r} is not present in input"))
                elif material_id in seen:
                    result.append(issue(path, "duplicate_material_id", f"material_id {material_id!r} is duplicated in this scene"))
                seen.add(material_id)
            layout_fields = [layout.field for layout in scene.text_layouts]
            for layout_index, field in enumerate(layout_fields):
                path = ("scenes", scene_index, "text_layouts", layout_index, "field")
                if layout_fields.count(field) > 1:
                    result.append(issue(path, "duplicate_text_layout_field", f"text layout field {field!r} is duplicated"))
                elif field == "hook" and scene_index != 0:
                    result.append(issue(path, "hook_layout_wrong_scene", "hook text layout is only allowed in the first scene"))
                elif field == "closing" and scene_index != len(value.scenes) - 1:
                    result.append(issue(path, "closing_layout_wrong_scene", "closing text layout is only allowed in the last scene"))
            if scene_index == 0 and "hook" not in layout_fields:
                result.append(issue(("scenes", scene_index, "text_layouts", "missing-hook"), "missing_hook_layout", "first scene must configure the required hook field"))
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
        provider=provider, contract_name=contract_name, prompt=json.loads(prompt), schema=DirectorDecision,
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
            text_layouts=[DirectorTextLayout.model_validate(layout.model_dump()) for layout in scene.text_layouts],
        ) for index, scene in enumerate(decision.scenes, 1)],
    )
    timing = compile_timing_plan(
        total_frames=plan.duration_seconds * project.fps,
        fps=project.fps,
        scenes=plan.scenes,
        project_width=project.width,
    )
    _persist(state, "director_plan.json", plan)
    _persist(state, "timing_plan.json", timing)
    if split_request:
        _persist(state, f"director_plan_split-{split_count:03d}.json", plan)
        _persist(state, f"timing_plan_split-{split_count:03d}.json", timing)
    return {
        "director_plan": plan, "timing_plan": timing,
        "copy_fit_decision": None, "scene_split_request": None,
        **({"revision_count": 0} if split_request else {}),
    }


def director_review_node(state: dict) -> dict:
    """Review compiled pages; prefer repagination and escalate true narrative splits."""
    provider = require_agent_provider("director")
    revision = state.get("revision_count", 0)
    contract_name = f"director_review_revision-{revision:03d}"
    reading_report = build_reading_load_report(
        state["viral_copy_plan"], state["timing_plan"], state["presentation_plan"],
    )
    prompt = json.dumps({
        "role": "Director Review",
        "question": "分页编译通过后，画面是否清晰；是否存在需要独立 scene 的多个叙事节点？",
        "hard_boundary": "不能直接修改总时长、FPS、scene、权重或帧区间；只能接受、要求 Copy 重分页，或请求 Director split。",
        "requirements": [
            "status 只能是 accepted、revise_copy 或 split_scene",
            "长文案优先用 paginate target 重新分页；只有分页仍不能解决时才用 compress target",
            "存在两个以上独立叙事节点时使用 split_scene，并明确 narrative_nodes",
            "所有 scene_id、page_index 和 field 必须引用输入中的真实值",
            "accepted 时 page_targets 和 split_targets 都必须为空",
            "不要使用配音、朗读时长或说话速度作为判断依据",
        ],
        "director_plan": state["director_plan"].model_dump(mode="json"),
        "timing_plan": state["timing_plan"].model_dump(mode="json"),
        "presentation_plan": state["presentation_plan"].model_dump(mode="json"),
        "viral_copy_plan": state["viral_copy_plan"].model_dump(mode="json"),
        "reading_load_report": reading_report,
    }, ensure_ascii=False)
    pages = {
        (scene["scene_id"], page_index): page
        for scene in reading_report["scenes"] for page_index, page in enumerate(scene["pages"])
    }
    scene_ids = set(pages_key[0] for pages_key in pages)
    def validate_review(value: CopyFitReviewDecision):
        result = []
        seen = set()
        if value.status == "accepted" and (value.page_targets or value.split_targets):
            result.append(issue(("page_targets",), "accepted_has_targets", "accepted review must use empty target arrays", related_paths=(("status",), ("split_targets",))))
        if value.status != "accepted" and not value.feedback:
            result.append(issue(("feedback",), "review_feedback_missing", "non-accepted review requires feedback"))
        if value.status == "revise_copy" and (not value.page_targets or value.split_targets):
            result.append(issue(("page_targets",), "copy_targets_invalid", "revise_copy requires page_targets and no split_targets", related_paths=(("status",), ("split_targets",))))
        if value.status == "split_scene" and (not value.split_targets or value.page_targets):
            result.append(issue(("split_targets",), "split_targets_invalid", "split_scene requires split_targets and no page_targets", related_paths=(("status",), ("page_targets",))))
        for index, target in enumerate(value.page_targets):
            key = (target.scene_id, target.page_index)
            page = pages.get(key)
            field = next((item for item in page["fields"] if item["field"] == target.field), None) if page else None
            if field is None:
                result.append(issue(("page_targets", index), "unknown_page_field", f"target {key + (target.field,)!r} is not present"))
            elif target.action == "compress":
                if target.max_display_units is None or target.max_display_units >= field["display_units"]:
                    result.append(issue(("page_targets", index, "max_display_units"), "non_actionable_target", "compress target must be lower than current display_units"))
            elif target.max_display_units is not None:
                result.append(issue(("page_targets", index, "max_display_units"), "paginate_has_limit", "paginate target must use null max_display_units"))
            target_key = key + (target.field,)
            if target_key in seen:
                result.append(issue(("page_targets", index), "duplicate_page_target", "page target is duplicated"))
            seen.add(target_key)
        for index, target in enumerate(value.split_targets):
            if target.scene_id not in scene_ids:
                result.append(issue(("split_targets", index, "scene_id"), "unknown_scene_id", f"scene_id {target.scene_id!r} is not present"))
        return result

    reviewed = StructuredAgentRunner().run(
        provider=provider, contract_name=contract_name, prompt=json.loads(prompt), schema=CopyFitReviewDecision,
        artifact_dir=state["project"].project_dir, semantic_validator=validate_review,
    )
    decision = CopyFitDecision(
        status=reviewed.status, feedback=reviewed.feedback,
        page_targets=[CopyFitPageTarget.model_validate(target.model_dump()) for target in reviewed.page_targets],
        split_targets=[SceneSplitTarget.model_validate(target.model_dump()) for target in reviewed.split_targets],
    )
    _persist(state, "copy_fit_decision.json", decision)
    _persist(state, f"copy_fit_decision_revision-{revision:03d}.json", decision)
    result = {"copy_fit_decision": decision}
    if decision.status == "revise_copy":
        result["revision_count"] = state.get("revision_count", 0) + 1
    elif decision.status == "split_scene":
        result["scene_split_request"] = decision
        result["scene_split_count"] = state.get("scene_split_count", 0) + 1
    return result


def _persist(state: dict, name: str, model) -> None:
    path = Path(state["project"].project_dir) / name
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(model.model_dump_json(indent=2), encoding="utf-8")
    temporary.replace(path)


def _mirror_contract_files(state: dict, contract_name: str, output_name: str) -> None:
    run_dir = Path(state["project"].project_dir) / "agent_runs" / contract_name
    response = run_dir / ("attempt-2.txt" if (run_dir / "attempt-2.txt").is_file() else "attempt-1.txt")
    if response.is_file():
        shutil.copyfile(response, Path(state["project"].project_dir) / f"{output_name}_response.txt")
    validation = run_dir / "validation.json"
    if validation.is_file():
        shutil.copyfile(validation, Path(state["project"].project_dir) / f"{output_name}_validation.json")
