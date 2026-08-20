import json
from pathlib import Path

import pytest

from content_creator.schemas import (
    CopyFitDecision, CopyPage, CopyPageText, CopyScene, DirectorPlan, DirectorScene, EditorialBeat,
    DirectorTextLayout, EditorialPlan, Material, ProjectContext, SceneTiming, SourceReference,
    SourceResult, SourceResults, TextFieldBudget, TimingPlan, ViralCopyPlan,
)
from content_creator.workflow import graph as graph_module
from content_creator.agents import animation_agent, content_agents
from content_creator.services.timing import compile_presentation_plan


def layouts(*fields):
    profiles = {"hook": "display", "title": "headline", "body": "body", "emphasis": "label", "closing": "display"}
    return [DirectorTextLayout(
        field=field, typography_profile=profiles[field], visibility_profile="standard",
        hierarchy_level="primary" if field in {"hook", "closing"} else "secondary",
    ) for field in fields]


def budgets(*fields):
    profiles = {"hook": "display", "title": "headline", "body": "body", "emphasis": "label", "closing": "display"}
    return [TextFieldBudget(
        field=field, typography_profile=profiles[field], visibility_profile="standard",
        hierarchy_level="primary" if field in {"hook", "closing"} else "secondary",
        font_size_px=40, max_lines=8, max_units_per_line=100,
        min_visible_frames=225, max_total_units=100,
    ) for field in fields]


def director_scene(**kwargs):
    return DirectorScene(text_layouts=kwargs.pop("text_layouts", layouts("hook", "title", "body")), **kwargs)


def fixture_state(tmp_path):
    ref = SourceReference(source_id="source-001", paragraph_index=0)
    material = Material(id="source-001-material-001", source_id="source-001", path="materials/a.webp", width=100, height=100)
    (tmp_path / "materials").mkdir()
    (tmp_path / "materials" / "a.webp").write_bytes(b"x")
    sources = SourceResults(sources=[SourceResult(source_id="source-001", url="https://example.com", title="标题", body="正文", materials=[material])])
    editorial = EditorialPlan(thesis="主题", audience="大众", narrative="叙事", title_direction="方向", beats=[EditorialBeat(id="b1", purpose="hook", point="观点", source_references=[ref], priority=10)])
    copy = ViralCopyPlan(final_title="测试标题", scenes=[CopyScene(scene_id="scene-1", pages=[CopyPage(
        page_id="scene-1-page-001", material_id="source-001-material-001",
        texts=[CopyPageText(field="hook", text="测试钩子"), CopyPageText(field="title", text="标题"), CopyPageText(field="body", text="正文内容")],
        source_references=[ref],
    )])])
    timing = TimingPlan(fps=30, duration_frames=450, scenes=[SceneTiming(
        scene_id="scene-1", start_frame=0, end_frame=450,
        field_budgets=budgets("hook", "title", "body"),
    )])
    context = ProjectContext(project_id="p", project_dir=str(tmp_path), urls=["https://example.com"])
    return context, sources, editorial, copy, timing


def test_copy_director_loop_is_bounded(tmp_path, monkeypatch):
    context, sources, editorial, copy, timing = fixture_state(tmp_path)
    calls = {"copy": 0, "review": 0}
    monkeypatch.setattr(graph_module, "source_node", lambda state: {"source_results": sources})
    monkeypatch.setattr(graph_module, "editorial_node", lambda state: {"editorial_plan": editorial})
    def copy_node(state):
        calls["copy"] += 1
        return {"viral_copy_plan": copy}
    def director_node(state):
        plan = DirectorPlan(width=1080, height=1920, fps=30, duration_seconds=15, duration_reason="单一核心信息", safe_area="四周80", background_atmosphere="深色", typography_hierarchy="标题正文", alignment_tendency="居中", rhythm="快", scenes=[director_scene(scene_id="scene-1", material_ids=["source-001-material-001"], duration_weight=1, image_intent="主体", camera_intent="推进", transition_intent="淡入", information_hierarchy="标题图片正文")])
        return {"director_plan": plan, "timing_plan": timing}
    def review_node(state):
        calls["review"] += 1
        revise = calls["review"] <= 2
        decision = CopyFitDecision(status="revise_copy" if revise else "accepted", feedback="重新分页" if revise else "")
        return {"copy_fit_decision": decision, **({"revision_count": state.get("revision_count", 0) + 1} if revise else {})}
    monkeypatch.setattr(graph_module, "copy_fitting_node", copy_node)
    monkeypatch.setattr(graph_module, "director_node", director_node)
    monkeypatch.setattr(graph_module, "director_review_node", review_node)
    monkeypatch.setattr(graph_module, "animation_node", lambda state: {"animation_artifact": "ok"})
    result = graph_module.build_graph().invoke({"project": context, "revision_count": 0})
    assert result["animation_artifact"] == "ok"
    assert calls == {"copy": 3, "review": 3}


def test_third_revision_request_fails(tmp_path, monkeypatch):
    context, sources, editorial, copy, timing = fixture_state(tmp_path)
    monkeypatch.setattr(graph_module, "source_node", lambda state: {"source_results": sources})
    monkeypatch.setattr(graph_module, "editorial_node", lambda state: {"editorial_plan": editorial})
    monkeypatch.setattr(graph_module, "copy_fitting_node", lambda state: {"viral_copy_plan": copy})
    plan = DirectorPlan(width=1080, height=1920, fps=30, duration_seconds=15, duration_reason="单一核心信息", safe_area="安全", background_atmosphere="深色", typography_hierarchy="层级", alignment_tendency="居中", rhythm="快", scenes=[director_scene(scene_id="scene-1", material_ids=["source-001-material-001"], duration_weight=1, image_intent="主体", camera_intent="推进", transition_intent="淡入", information_hierarchy="层级")])
    monkeypatch.setattr(graph_module, "director_node", lambda state: {"director_plan": plan, "timing_plan": timing})
    monkeypatch.setattr(graph_module, "director_review_node", lambda state: {"copy_fit_decision": CopyFitDecision(status="revise_copy", feedback="重新分页"), "revision_count": state.get("revision_count", 0) + 1})
    monkeypatch.setattr(graph_module, "animation_node", lambda state: {"animation_artifact": "unexpected"})
    with pytest.raises(RuntimeError, match="exceeded 2"):
        graph_module.build_graph().invoke({"project": context, "revision_count": 0})


def test_animation_prompt_receives_complete_agent_flow(tmp_path, monkeypatch):
    context, sources, editorial, copy, timing = fixture_state(tmp_path)
    (tmp_path / "runtime").mkdir()
    (tmp_path / "runtime" / "gsap.min.js").write_text("gsap", encoding="utf-8")
    director = DirectorPlan(width=1080, height=1920, fps=30, duration_seconds=15, duration_reason="单一核心信息", safe_area="四周80", background_atmosphere="深色", typography_hierarchy="标题正文", alignment_tendency="居中", rhythm="快", scenes=[director_scene(scene_id="scene-1", material_ids=["source-001-material-001"], duration_weight=1, image_intent="主体", camera_intent="推进", transition_intent="淡入", information_hierarchy="标题图片正文")])
    html = """<!doctype html><html><head><script src="runtime/gsap.min.js"></script></head><body><div id="box"></div><script>
window.__ANIMATION_READY__=false;window.__ANIMATION_META__={width:1080,height:1920,fps:30,durationFrames:450};
const masterTimeline=gsap.timeline({paused:true});masterTimeline.to('#box',{opacity:1,duration:1});
window.renderFrame=async function(frame){const fps=window.__ANIMATION_META__.fps;const time=frame/fps;masterTimeline.time(time,false);await document.fonts.ready};
document.fonts.ready.then(()=>window.__ANIMATION_READY__=true);
</script></body></html>"""

    class Provider:
        model_name = "animation-model"
        def complete_multimodal_text(self, prompt, image_paths):
            assert image_paths == [str(tmp_path / "materials" / "a.webp")]
            return html

    monkeypatch.setattr(animation_agent, "require_agent_provider", lambda _name: Provider())
    result = animation_agent.animation_node({"project": context, "source_results": sources, "editorial_plan": editorial, "viral_copy_plan": copy, "timing_plan": timing, "presentation_plan": compile_presentation_plan(copy, timing), "director_plan": director, "revision_count": 0})
    prompt = json.loads((tmp_path / "animation_prompt.json").read_text(encoding="utf-8"))
    assert set(prompt["inputs"]) == {"source_results", "editorial_plan", "viral_copy_plan", "timing_plan", "presentation_plan", "director_plan", "materials", "fonts"}
    assert "masterTimeline.time(time, false)" in prompt["runtime_contract"]["render_frame"]
    assert result["animation_artifact"].model == "animation-model"
    assert result["animation_artifact"].artifact_metadata["contract_repair_count"] == 0
    assert (tmp_path / "animation.html").is_file()
    assert (tmp_path / "animation_response.txt").read_text(encoding="utf-8") == html
    assert (tmp_path / "animation_response_attempt-1.txt").read_text(encoding="utf-8") == html
    assert json.loads((tmp_path / "animation_validation.json").read_text(encoding="utf-8")) == {
        "status": "passed",
        "model": "animation-model",
        "attempts": [{"attempt": 1, "status": "passed", "error": None}],
    }


def test_animation_validation_failure_preserves_raw_response_and_detail(tmp_path, monkeypatch):
    context, sources, editorial, copy, timing = fixture_state(tmp_path)
    (tmp_path / "runtime").mkdir()
    (tmp_path / "runtime" / "gsap.min.js").write_text("gsap", encoding="utf-8")
    director = DirectorPlan(width=1080, height=1920, fps=30, duration_seconds=15, duration_reason="单一核心信息", safe_area="四周80", background_atmosphere="深色", typography_hierarchy="标题正文", alignment_tendency="居中", rhythm="快", scenes=[director_scene(scene_id="scene-1", material_ids=["source-001-material-001"], duration_weight=1, image_intent="主体", camera_intent="推进", transition_intent="淡入", information_hierarchy="标题图片正文")])
    invalid_html = """<!doctype html><html><head><script src="runtime/gsap.min.js"></script></head><body><script>
window.__ANIMATION_READY__=false;window.__ANIMATION_META__={width:1080,height:1920,fps:30,durationFrames:450};
const masterTimeline=gsap.timeline({paused:true});
window.renderFrame=async function(frame){const fps=window.__ANIMATION_META__.fps;const time=frame/fps;masterTimeline.seek(time);await document.fonts.ready};
document.fonts.ready.then(()=>window.__ANIMATION_READY__=true);
</script></body></html>"""

    class Provider:
        model_name = "animation-model"

        def complete_multimodal_text(self, _prompt, _image_paths):
            return invalid_html

    monkeypatch.setattr(animation_agent, "require_agent_provider", lambda _name: Provider())
    with pytest.raises(ValueError, match="found masterTimeline.seek"):
        animation_agent.animation_node({"project": context, "source_results": sources, "editorial_plan": editorial, "viral_copy_plan": copy, "timing_plan": timing, "presentation_plan": compile_presentation_plan(copy, timing), "director_plan": director, "revision_count": 0})

    assert (tmp_path / "animation_response.txt").read_text(encoding="utf-8") == invalid_html
    validation = json.loads((tmp_path / "animation_validation.json").read_text(encoding="utf-8"))
    assert validation["status"] == "failed"
    assert validation["model"] == "animation-model"
    assert "found masterTimeline.seek" in validation["error"]
    assert [attempt["status"] for attempt in validation["attempts"]] == ["failed", "failed"]
    assert (tmp_path / "animation_response_attempt-1.txt").read_text(encoding="utf-8") == invalid_html
    assert (tmp_path / "animation_response_attempt-2.txt").read_text(encoding="utf-8") == invalid_html
    assert not (tmp_path / "animation.html").exists()


def test_animation_repairs_timeline_alias_once_without_redesigning_html(tmp_path, monkeypatch):
    context, sources, editorial, copy, timing = fixture_state(tmp_path)
    (tmp_path / "runtime").mkdir()
    (tmp_path / "runtime" / "gsap.min.js").write_text("gsap", encoding="utf-8")
    director = DirectorPlan(width=1080, height=1920, fps=30, duration_seconds=15, duration_reason="单一核心信息", safe_area="安全", background_atmosphere="深色", typography_hierarchy="标题正文", alignment_tendency="居中", rhythm="快", scenes=[director_scene(scene_id="scene-1", material_ids=["source-001-material-001"], duration_weight=1, image_intent="主体", camera_intent="推进", transition_intent="淡入", information_hierarchy="标题图片正文")])
    alias_html = """<!doctype html><html><head><style>#box{color:red}</style><script src="runtime/gsap.min.js"></script></head><body><div id="box">原文</div><script>
window.__ANIMATION_READY__=false;window.__ANIMATION_META__={width:1080,height:1920,fps:30,durationFrames:450};
const tl=gsap.timeline({paused:true});window.masterTimeline=tl;tl.to('#box',{opacity:1,duration:1},2);
window.renderFrame=async function(frame){const fps=window.__ANIMATION_META__.fps;const time=frame/fps;masterTimeline.time(time,false);await document.fonts.ready};
document.fonts.ready.then(()=>window.__ANIMATION_READY__=true);
</script></body></html>"""
    repaired_html = alias_html.replace("const tl=", "const masterTimeline=").replace("window.masterTimeline=tl;", "").replace("tl.to", "masterTimeline.to")

    class Provider:
        model_name = "animation-model"

        def __init__(self):
            self.responses = iter((alias_html, repaired_html))
            self.prompts = []

        def complete_multimodal_text(self, prompt, _image_paths):
            self.prompts.append(json.loads(prompt))
            return next(self.responses)

    provider = Provider()
    monkeypatch.setattr(animation_agent, "require_agent_provider", lambda _name: provider)
    result = animation_agent.animation_node({"project": context, "source_results": sources, "editorial_plan": editorial, "viral_copy_plan": copy, "timing_plan": timing, "presentation_plan": compile_presentation_plan(copy, timing), "director_plan": director, "revision_count": 0})

    assert result["animation_artifact"].artifact_metadata["contract_repair_count"] == 1
    assert (tmp_path / "animation.html").read_text(encoding="utf-8") == repaired_html
    assert (tmp_path / "animation_response.txt").read_text(encoding="utf-8") == repaired_html
    validation = json.loads((tmp_path / "animation_validation.json").read_text(encoding="utf-8"))
    assert validation["status"] == "passed_after_repair"
    assert [attempt["status"] for attempt in validation["attempts"]] == ["failed", "passed"]
    repair_prompt = provider.prompts[1]
    assert repair_prompt["contract_error"].startswith("A paused GSAP masterTimeline is required")
    assert "DOM 结构" in repair_prompt["repair_scope"]["immutable"]


def test_animation_repair_rejects_visual_or_timing_changes(tmp_path, monkeypatch):
    context, sources, editorial, copy, timing = fixture_state(tmp_path)
    (tmp_path / "runtime").mkdir()
    (tmp_path / "runtime" / "gsap.min.js").write_text("gsap", encoding="utf-8")
    director = DirectorPlan(width=1080, height=1920, fps=30, duration_seconds=15, duration_reason="原因", safe_area="安全", background_atmosphere="深色", typography_hierarchy="层级", alignment_tendency="居中", rhythm="快", scenes=[director_scene(scene_id="scene-1", material_ids=["source-001-material-001"], duration_weight=1, image_intent="主体", camera_intent="推进", transition_intent="淡入", information_hierarchy="层级")])
    alias_html = """<!doctype html><html><head><style>#box{color:red}</style><script src="runtime/gsap.min.js"></script></head><body><div id="box">原文</div><script>
window.__ANIMATION_READY__=false;window.__ANIMATION_META__={width:1080,height:1920,fps:30,durationFrames:450};const tl=gsap.timeline({paused:true});window.masterTimeline=tl;tl.to('#box',{opacity:1,duration:1},2);window.renderFrame=async function(frame){const fps=window.__ANIMATION_META__.fps;const time=frame/fps;masterTimeline.time(time,false);await document.fonts.ready};document.fonts.ready.then(()=>window.__ANIMATION_READY__=true);
</script></body></html>"""
    changed = alias_html.replace("const tl=", "const masterTimeline=").replace("window.masterTimeline=tl;", "").replace("tl.to", "masterTimeline.to").replace("duration:1", "duration:2")

    class Provider:
        model_name = "animation-model"
        def __init__(self): self.responses = iter((alias_html, changed))
        def complete_multimodal_text(self, _prompt, _paths): return next(self.responses)

    monkeypatch.setattr(animation_agent, "require_agent_provider", lambda _name: Provider())
    with pytest.raises(ValueError, match="outside masterTimeline"):
        animation_agent.animation_node({"project": context, "source_results": sources, "editorial_plan": editorial, "viral_copy_plan": copy, "timing_plan": timing, "presentation_plan": compile_presentation_plan(copy, timing), "director_plan": director, "revision_count": 0})


def test_animation_provider_error_does_not_trigger_contract_repair(tmp_path, monkeypatch):
    context, sources, editorial, copy, timing = fixture_state(tmp_path)
    director = DirectorPlan(width=1080, height=1920, fps=30, duration_seconds=15, duration_reason="原因", safe_area="安全", background_atmosphere="深色", typography_hierarchy="层级", alignment_tendency="居中", rhythm="快", scenes=[director_scene(scene_id="scene-1", material_ids=["source-001-material-001"], duration_weight=1, image_intent="主体", camera_intent="推进", transition_intent="淡入", information_hierarchy="层级")])

    class Provider:
        model_name = "animation-model"
        calls = 0
        def complete_multimodal_text(self, _prompt, _paths):
            self.calls += 1
            raise TimeoutError("gateway timeout")

    provider = Provider()
    monkeypatch.setattr(animation_agent, "require_agent_provider", lambda _name: provider)
    with pytest.raises(TimeoutError, match="gateway timeout"):
        animation_agent.animation_node({"project": context, "source_results": sources, "editorial_plan": editorial, "viral_copy_plan": copy, "timing_plan": timing, "presentation_plan": compile_presentation_plan(copy, timing), "director_plan": director, "revision_count": 0})
    assert provider.calls == 1
    validation = json.loads((tmp_path / "animation_validation.json").read_text(encoding="utf-8"))
    assert validation["status"] == "invocation_failed"
    assert len(validation["attempts"]) == 1


def test_director_model_outputs_seconds_only_and_python_compiles_frames(tmp_path, monkeypatch):
    context, sources, editorial, _, _ = fixture_state(tmp_path)

    class Provider:
        def complete_json(self, prompt):
            payload = json.loads(prompt)
            properties = payload["agent_output_contract"]["output_schema"]["properties"]
            assert "duration_seconds" in properties
            assert "duration_frames" not in properties
            return json.dumps({
                "duration_seconds": 15, "duration_reason": "一个核心 beat 和一张可用素材",
                "safe_area": "四周80", "background_atmosphere": "深色",
                "typography_hierarchy": "标题正文", "alignment_tendency": "居中", "rhythm": "快",
                "scenes": [{
                    "material_ids": ["source-001-material-001"], "duration_weight": 1,
                    "image_intent": "主体", "camera_intent": "推进", "transition_intent": "淡入",
                    "information_hierarchy": "标题图片正文", "visual_density": "medium",
                    "text_layouts": [
                        {"field": "hook", "typography_profile": "display", "visibility_profile": "standard", "hierarchy_level": "primary"},
                        {"field": "title", "typography_profile": "headline", "visibility_profile": "standard", "hierarchy_level": "secondary"},
                        {"field": "body", "typography_profile": "body", "visibility_profile": "persistent", "hierarchy_level": "supporting"},
                    ],
                }],
            }, ensure_ascii=False)

    monkeypatch.setattr(content_agents, "require_agent_provider", lambda _name: Provider())
    result = content_agents.director_node({"project": context, "source_results": sources, "editorial_plan": editorial})
    assert result["director_plan"].duration_frames == 15 * context.fps
    assert result["director_plan"].scenes[0].scene_id == "scene-001"
    assert result["timing_plan"].duration_frames == 15 * context.fps
    persisted = json.loads((tmp_path / "director_plan.json").read_text(encoding="utf-8"))
    assert persisted["duration_seconds"] == 15
    assert persisted["duration_frames"] == 450


def test_copy_fitting_cannot_smuggle_timing_and_preserves_diagnostics(tmp_path, monkeypatch):
    context, sources, editorial, copy, timing = fixture_state(tmp_path)
    director = DirectorPlan(
        duration_seconds=15, duration_reason="单一 beat", safe_area="安全", background_atmosphere="深色",
        typography_hierarchy="标题正文", alignment_tendency="居中", rhythm="快",
        scenes=[director_scene(scene_id="scene-1", material_ids=["source-001-material-001"], duration_weight=1,
            image_intent="主体", camera_intent="推进", transition_intent="淡入", information_hierarchy="标题正文")],
    )
    raw = json.dumps(copy.model_dump(mode="json") | {"timing_plan": timing.model_dump(mode="json")}, ensure_ascii=False)

    class Provider:
        def complete_json(self, _prompt):
            return raw

    monkeypatch.setattr(content_agents, "require_agent_provider", lambda _name: Provider())
    with pytest.raises(Exception, match="timing_plan"):
        content_agents.copy_fitting_node({
            "project": context, "source_results": sources, "editorial_plan": editorial,
            "director_plan": director, "timing_plan": timing, "revision_count": 0,
        })
    assert (tmp_path / "copy_fitting_response.txt").read_text(encoding="utf-8") == raw
    validation = json.loads((tmp_path / "copy_fitting_validation.json").read_text(encoding="utf-8"))
    assert validation["status"] == "failed"
    assert "timing_plan" in validation["error"]


def test_editorial_uses_python_beat_ids_and_persists_contract(tmp_path, monkeypatch):
    context, sources, _, _, _ = fixture_state(tmp_path)
    raw = json.dumps({
        "thesis": "主题", "audience": "大众", "narrative": "叙事", "title_direction": "方向",
        "mood": "informative", "topics": [],
        "beats": [{"purpose": "hook", "point": "观点", "source_references": [{"source_id": "source-001", "paragraph_index": 0}], "priority": 10}],
    }, ensure_ascii=False)

    class Provider:
        def complete_json(self, _prompt): return raw

    monkeypatch.setattr(content_agents, "require_agent_provider", lambda _name: Provider())
    result = content_agents.editorial_node({"project": context, "source_results": sources})
    assert result["editorial_plan"].beats[0].id == "beat-001"
    assert json.loads((tmp_path / "agent_runs" / "editorial" / "validation.json").read_text())["status"] == "passed"


def test_director_repairs_incomplete_fourth_scene_without_model_generated_ids(tmp_path, monkeypatch):
    context, sources, editorial, _, _ = fixture_state(tmp_path)
    scene = {
        "material_ids": ["source-001-material-001"], "duration_weight": 1,
        "image_intent": "主体", "camera_intent": "推进", "transition_intent": "淡入",
        "information_hierarchy": "标题正文", "visual_density": "medium",
        "text_layouts": [{"field": "title", "typography_profile": "headline", "visibility_profile": "standard", "hierarchy_level": "secondary"}],
    }
    first_scene = scene | {
        "text_layouts": [{"field": "hook", "typography_profile": "display", "visibility_profile": "standard", "hierarchy_level": "primary"}],
    }
    base = {
        "duration_seconds": 30, "duration_reason": "五个信息点", "safe_area": "安全",
        "background_atmosphere": "深色", "typography_hierarchy": "标题正文",
        "alignment_tendency": "居中", "rhythm": "快",
    }
    incomplete = base | {"scenes": [first_scene, scene, scene, {
        "image_intent": "收束", "camera_intent": "静止", "transition_intent": "淡出",
        "information_hierarchy": "结论", "visual_density": "low",
        "text_layouts": [{"field": "title", "typography_profile": "headline", "visibility_profile": "standard", "hierarchy_level": "secondary"}],
    }]}
    repaired = base | {"scenes": [first_scene, scene, scene, {
        "material_ids": ["source-001-material-001"], "duration_weight": 0.8,
        "image_intent": "收束", "camera_intent": "静止", "transition_intent": "淡出",
        "information_hierarchy": "结论", "visual_density": "low",
        "text_layouts": [{"field": "title", "typography_profile": "headline", "visibility_profile": "standard", "hierarchy_level": "secondary"}],
    }]}

    class Provider:
        def __init__(self): self.responses = iter([incomplete, repaired])
        def complete_json(self, _prompt): return json.dumps(next(self.responses), ensure_ascii=False)

    monkeypatch.setattr(content_agents, "require_agent_provider", lambda _name: Provider())
    result = content_agents.director_node({"project": context, "source_results": sources, "editorial_plan": editorial})
    assert [scene.scene_id for scene in result["director_plan"].scenes] == [f"scene-{index:03d}" for index in range(1, 5)]
    assert result["timing_plan"].duration_frames == 900
    validation = json.loads((tmp_path / "agent_runs" / "director" / "validation.json").read_text())
    assert validation["status"] == "passed_after_repair"
    assert {item["path"] for item in validation["attempts"][0]["issues"]} == {
        "scenes.3.material_ids", "scenes.3.duration_weight",
    }


def test_copy_and_review_use_locked_scene_ids(tmp_path, monkeypatch):
    context, sources, editorial, _, timing = fixture_state(tmp_path)
    timing = timing.model_copy(update={
        "scenes": [timing.scenes[0].model_copy(update={"scene_id": "scene-001"})],
    })
    director = DirectorPlan(
        duration_seconds=15, duration_reason="单一 beat", safe_area="安全", background_atmosphere="深色",
        typography_hierarchy="标题正文", alignment_tendency="居中", rhythm="快",
        scenes=[director_scene(scene_id="scene-001", material_ids=["source-001-material-001"], duration_weight=1,
            image_intent="主体", camera_intent="推进", transition_intent="淡入", information_hierarchy="标题正文")],
    )
    copy_raw = {
        "final_title": "测试标题",
        "scenes": [{"scene_id": "scene-001", "pages": [{
            "material_id": "source-001-material-001",
            "texts": [
                {"field": "hook", "text": "测试钩子"},
                {"field": "title", "text": "标题"},
                {"field": "body", "text": "正文"},
            ],
            "source_references": [{"source_id": "source-001", "paragraph_index": 0}],
        }]}],
    }
    review_raw = {"status": "accepted", "feedback": "", "page_targets": [], "split_targets": []}

    class Provider:
        def __init__(self, value): self.value = value
        def complete_json(self, _prompt): return json.dumps(self.value, ensure_ascii=False)

    providers = iter([Provider(copy_raw), Provider(review_raw)])
    monkeypatch.setattr(content_agents, "require_agent_provider", lambda _name: next(providers))
    state = {"project": context, "source_results": sources, "editorial_plan": editorial, "director_plan": director, "timing_plan": timing, "revision_count": 0}
    copy_result = content_agents.copy_fitting_node(state)
    presentation = compile_presentation_plan(copy_result["viral_copy_plan"], timing)
    review_result = content_agents.director_review_node(state | copy_result | {"presentation_plan": presentation})
    assert copy_result["viral_copy_plan"].scenes[0].scene_id == "scene-001"
    assert review_result["copy_fit_decision"].status == "accepted"
    assert review_result["copy_fit_decision"].page_targets == []


def test_copy_fitting_repairs_long_text_by_adding_a_page(tmp_path, monkeypatch):
    context, sources, editorial, _, timing = fixture_state(tmp_path)
    director = DirectorPlan(
        duration_seconds=15, duration_reason="单一 beat", safe_area="安全", background_atmosphere="深色",
        typography_hierarchy="标题正文", alignment_tendency="居中", rhythm="快",
        scenes=[director_scene(
            scene_id="scene-1", material_ids=["source-001-material-001"], duration_weight=1,
            image_intent="主体", camera_intent="推进", transition_intent="淡入", information_hierarchy="标题正文",
        )],
    )
    reference = [{"source_id": "source-001", "paragraph_index": 0}]
    long_body = "长" * 120
    first = {
        "final_title": "测试标题", "scenes": [{"scene_id": "scene-1", "pages": [{
            "material_id": "source-001-material-001",
            "texts": [
                {"field": "hook", "text": "测试钩子"}, {"field": "title", "text": "标题"},
                {"field": "body", "text": long_body},
            ],
            "source_references": reference,
        }]}],
    }
    repaired = {
        "final_title": "测试标题", "scenes": [{"scene_id": "scene-1", "pages": [
            {
                "material_id": "source-001-material-001",
                "texts": [
                    {"field": "hook", "text": "测试钩子"}, {"field": "title", "text": "标题"},
                    {"field": "body", "text": "长" * 60},
                ],
                "source_references": reference,
            },
            {
                "material_id": "source-001-material-001",
                "texts": [{"field": "body", "text": "长" * 60}],
                "source_references": reference,
            },
        ]}],
    }

    class Provider:
        def __init__(self): self.responses = iter((first, repaired))
        def complete_json(self, _prompt): return json.dumps(next(self.responses), ensure_ascii=False)

    monkeypatch.setattr(content_agents, "require_agent_provider", lambda _name: Provider())
    result = content_agents.copy_fitting_node({
        "project": context, "source_results": sources, "editorial_plan": editorial,
        "director_plan": director, "timing_plan": timing, "revision_count": 0,
    })
    copy = result["viral_copy_plan"]
    assert len(copy.scenes[0].pages) == 2
    assert [page.material_id for page in copy.scenes[0].pages] == ["source-001-material-001"] * 2
    assert compile_presentation_plan(copy, timing).scenes[0].pages[-1].end_frame == 450
    validation = json.loads((tmp_path / "agent_runs" / "copy_fitting_revision-000" / "validation.json").read_text())
    assert validation["status"] == "passed_after_repair"


def test_presentation_capacity_failure_requests_one_scene_split(tmp_path):
    context, _, _, copy, timing = fixture_state(tmp_path)
    base_page = copy.scenes[0].pages[0]
    overloaded = copy.model_copy(update={
        "scenes": [copy.scenes[0].model_copy(update={
            "pages": [base_page.model_copy(update={"page_id": f"scene-1-page-{index:03d}"}) for index in range(1, 4)],
        })],
    })
    result = graph_module.presentation_node({
        "project": context, "viral_copy_plan": overloaded, "timing_plan": timing,
        "scene_split_count": 0,
    })
    assert result["copy_fit_decision"].status == "split_scene"
    assert result["scene_split_count"] == 1
    assert result["scene_split_request"].split_targets[0].scene_id == "scene-1"
    validation = json.loads((tmp_path / "presentation_validation.json").read_text())
    assert validation["status"] == "scene_split_required"


def test_director_scene_split_preserves_duration_and_recompiles_timing(tmp_path, monkeypatch):
    context, sources, editorial, _, timing = fixture_state(tmp_path)
    previous = DirectorPlan(
        duration_seconds=15, duration_reason="单一场景容量不足", safe_area="安全", background_atmosphere="深色",
        typography_hierarchy="标题正文", alignment_tendency="居中", rhythm="快",
        scenes=[director_scene(
            scene_id="scene-001", material_ids=["source-001-material-001"], duration_weight=1,
            image_intent="主体", camera_intent="推进", transition_intent="淡入", information_hierarchy="两个节点",
        )],
    )
    request = CopyFitDecision(
        status="split_scene", feedback="两个独立节点",
        split_targets=[graph_module.SceneSplitTarget(
            scene_id="scene-001", reason="两个独立节点", narrative_nodes=["节点一", "节点二"],
        )],
    )
    response = {
        "duration_seconds": 15, "duration_reason": "保持总时长并拆分节点",
        "safe_area": "安全", "background_atmosphere": "深色", "typography_hierarchy": "标题正文",
        "alignment_tendency": "居中", "rhythm": "快",
        "scenes": [
            {
                "material_ids": ["source-001-material-001"], "duration_weight": 1,
                "image_intent": "节点一", "camera_intent": "推进", "transition_intent": "切换",
                "information_hierarchy": "节点一", "visual_density": "medium",
                "text_layouts": [{"field": "hook", "typography_profile": "display", "visibility_profile": "brief", "hierarchy_level": "primary"}],
            },
            {
                "material_ids": ["source-001-material-001"], "duration_weight": 1,
                "image_intent": "节点二", "camera_intent": "静止", "transition_intent": "淡出",
                "information_hierarchy": "节点二", "visual_density": "low", "text_layouts": [],
            },
        ],
    }

    class Provider:
        def complete_json(self, _prompt): return json.dumps(response, ensure_ascii=False)

    monkeypatch.setattr(content_agents, "require_agent_provider", lambda _name: Provider())
    result = content_agents.director_node({
        "project": context, "source_results": sources, "editorial_plan": editorial,
        "director_plan": previous, "timing_plan": timing, "scene_split_request": request,
        "scene_split_count": 1, "revision_count": 2,
    })
    assert result["director_plan"].duration_seconds == previous.duration_seconds
    assert len(result["director_plan"].scenes) == 2
    assert result["timing_plan"].duration_frames == previous.duration_frames
    assert result["revision_count"] == 0
    assert (tmp_path / "director_plan_split-001.json").is_file()
