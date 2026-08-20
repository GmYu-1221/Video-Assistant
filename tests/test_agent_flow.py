import json
from pathlib import Path

import pytest

from content_creator.schemas import (
    CopyFitDecision, CopyScene, DirectorPlan, DirectorScene, EditorialBeat,
    EditorialPlan, Material, ProjectContext, SceneTiming, SourceReference,
    SourceResult, SourceResults, TimingPlan, ViralCopyPlan,
)
from content_creator.workflow import graph as graph_module
from content_creator.agents import animation_agent, content_agents


def fixture_state(tmp_path):
    ref = SourceReference(source_id="source-001", paragraph_index=0)
    material = Material(id="source-001-material-001", source_id="source-001", path="materials/a.webp", width=100, height=100)
    (tmp_path / "materials").mkdir()
    (tmp_path / "materials" / "a.webp").write_bytes(b"x")
    sources = SourceResults(sources=[SourceResult(source_id="source-001", url="https://example.com", title="标题", body="正文", materials=[material])])
    editorial = EditorialPlan(thesis="主题", audience="大众", narrative="叙事", title_direction="方向", beats=[EditorialBeat(id="b1", purpose="hook", point="观点", source_references=[ref], priority=10)])
    copy = ViralCopyPlan(final_title="测试标题", hook="测试钩子", scenes=[CopyScene(scene_id="scene-1", title="标题", body="正文内容", source_references=[ref])])
    timing = TimingPlan(fps=30, duration_frames=450, scenes=[SceneTiming(scene_id="scene-1", start_frame=0, end_frame=450, text_budget=105)])
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
        plan = DirectorPlan(width=1080, height=1920, fps=30, duration_seconds=15, duration_reason="单一核心信息", safe_area="四周80", background_atmosphere="深色", typography_hierarchy="标题正文", alignment_tendency="居中", rhythm="快", scenes=[DirectorScene(scene_id="scene-1", material_ids=["source-001-material-001"], duration_weight=1, image_intent="主体", camera_intent="推进", transition_intent="淡入", information_hierarchy="标题图片正文")])
        return {"director_plan": plan, "timing_plan": timing}
    def review_node(state):
        calls["review"] += 1
        revise = calls["review"] <= 2
        decision = CopyFitDecision(status="revise" if revise else "accepted", feedback="压缩" if revise else "")
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
    plan = DirectorPlan(width=1080, height=1920, fps=30, duration_seconds=15, duration_reason="单一核心信息", safe_area="安全", background_atmosphere="深色", typography_hierarchy="层级", alignment_tendency="居中", rhythm="快", scenes=[DirectorScene(scene_id="scene-1", material_ids=["source-001-material-001"], duration_weight=1, image_intent="主体", camera_intent="推进", transition_intent="淡入", information_hierarchy="层级")])
    monkeypatch.setattr(graph_module, "director_node", lambda state: {"director_plan": plan, "timing_plan": timing})
    monkeypatch.setattr(graph_module, "director_review_node", lambda state: {"copy_fit_decision": CopyFitDecision(status="revise", feedback="压缩"), "revision_count": state.get("revision_count", 0) + 1})
    monkeypatch.setattr(graph_module, "animation_node", lambda state: {"animation_artifact": "unexpected"})
    with pytest.raises(RuntimeError, match="exceeded 2"):
        graph_module.build_graph().invoke({"project": context, "revision_count": 0})


def test_animation_prompt_receives_complete_agent_flow(tmp_path, monkeypatch):
    context, sources, editorial, copy, timing = fixture_state(tmp_path)
    (tmp_path / "runtime").mkdir()
    (tmp_path / "runtime" / "gsap.min.js").write_text("gsap", encoding="utf-8")
    director = DirectorPlan(width=1080, height=1920, fps=30, duration_seconds=15, duration_reason="单一核心信息", safe_area="四周80", background_atmosphere="深色", typography_hierarchy="标题正文", alignment_tendency="居中", rhythm="快", scenes=[DirectorScene(scene_id="scene-1", material_ids=["source-001-material-001"], duration_weight=1, image_intent="主体", camera_intent="推进", transition_intent="淡入", information_hierarchy="标题图片正文")])
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
    result = animation_agent.animation_node({"project": context, "source_results": sources, "editorial_plan": editorial, "viral_copy_plan": copy, "timing_plan": timing, "director_plan": director, "revision_count": 0})
    prompt = json.loads((tmp_path / "animation_prompt.json").read_text(encoding="utf-8"))
    assert set(prompt["inputs"]) == {"source_results", "editorial_plan", "viral_copy_plan", "timing_plan", "director_plan", "materials", "fonts"}
    assert "masterTimeline.time(time, false)" in prompt["runtime_contract"]["render_frame"]
    assert result["animation_artifact"].model == "animation-model"
    assert (tmp_path / "animation.html").is_file()
    assert (tmp_path / "animation_response.txt").read_text(encoding="utf-8") == html
    assert json.loads((tmp_path / "animation_validation.json").read_text(encoding="utf-8")) == {
        "status": "passed",
        "model": "animation-model",
    }


def test_animation_validation_failure_preserves_raw_response_and_detail(tmp_path, monkeypatch):
    context, sources, editorial, copy, timing = fixture_state(tmp_path)
    (tmp_path / "runtime").mkdir()
    (tmp_path / "runtime" / "gsap.min.js").write_text("gsap", encoding="utf-8")
    director = DirectorPlan(width=1080, height=1920, fps=30, duration_seconds=15, duration_reason="单一核心信息", safe_area="四周80", background_atmosphere="深色", typography_hierarchy="标题正文", alignment_tendency="居中", rhythm="快", scenes=[DirectorScene(scene_id="scene-1", material_ids=["source-001-material-001"], duration_weight=1, image_intent="主体", camera_intent="推进", transition_intent="淡入", information_hierarchy="标题图片正文")])
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
        animation_agent.animation_node({"project": context, "source_results": sources, "editorial_plan": editorial, "viral_copy_plan": copy, "timing_plan": timing, "director_plan": director, "revision_count": 0})

    assert (tmp_path / "animation_response.txt").read_text(encoding="utf-8") == invalid_html
    validation = json.loads((tmp_path / "animation_validation.json").read_text(encoding="utf-8"))
    assert validation["status"] == "failed"
    assert validation["model"] == "animation-model"
    assert "found masterTimeline.seek" in validation["error"]
    assert not (tmp_path / "animation.html").exists()


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
        scenes=[DirectorScene(scene_id="scene-1", material_ids=["source-001-material-001"], duration_weight=1,
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
    }
    base = {
        "duration_seconds": 30, "duration_reason": "五个信息点", "safe_area": "安全",
        "background_atmosphere": "深色", "typography_hierarchy": "标题正文",
        "alignment_tendency": "居中", "rhythm": "快",
    }
    incomplete = base | {"scenes": [scene, scene, scene, {
        "image_intent": "收束", "camera_intent": "静止", "transition_intent": "淡出",
        "information_hierarchy": "结论", "visual_density": "low",
    }]}
    repaired = base | {"scenes": [scene, scene, scene, {
        "material_ids": ["source-001-material-001"], "duration_weight": 0.8,
        "image_intent": "收束", "camera_intent": "静止", "transition_intent": "淡出",
        "information_hierarchy": "结论", "visual_density": "low",
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
    director = DirectorPlan(
        duration_seconds=15, duration_reason="单一 beat", safe_area="安全", background_atmosphere="深色",
        typography_hierarchy="标题正文", alignment_tendency="居中", rhythm="快",
        scenes=[DirectorScene(scene_id="scene-001", material_ids=["source-001-material-001"], duration_weight=1,
            image_intent="主体", camera_intent="推进", transition_intent="淡入", information_hierarchy="标题正文")],
    )
    copy_raw = {
        "final_title": "测试标题", "hook": "测试钩子", "closing": "",
        "scenes": [{"scene_id": "scene-001", "title": "标题", "body": "正文", "emphasis": "",
            "source_references": [{"source_id": "source-001", "paragraph_index": 0}]}],
    }
    review_raw = {"status": "accepted", "feedback": "", "targets": []}

    class Provider:
        def __init__(self, value): self.value = value
        def complete_json(self, _prompt): return json.dumps(self.value, ensure_ascii=False)

    providers = iter([Provider(copy_raw), Provider(review_raw)])
    monkeypatch.setattr(content_agents, "require_agent_provider", lambda _name: next(providers))
    state = {"project": context, "source_results": sources, "editorial_plan": editorial, "director_plan": director, "timing_plan": timing, "revision_count": 0}
    copy_result = content_agents.copy_fitting_node(state)
    review_result = content_agents.director_review_node(state | copy_result)
    assert copy_result["viral_copy_plan"].scenes[0].scene_id == "scene-001"
    assert review_result["copy_fit_decision"].status == "accepted"
    assert review_result["copy_fit_decision"].scene_targets == {}
