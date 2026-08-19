from hashlib import sha256

import pytest

from content_creator.schemas import CaptionTemplateSlotBinding, ViralCopyPlan, ViralCopyUnit, ViralTitleCandidate
from content_creator.services.caption_templates import build_caption_template_plan, get_caption_template, select_caption_template, validate_caption_template_plan


def _copy_plan():
    titles = [ViralTitleCandidate(candidate_id=f"t{i}", text=f"测试标题{i}", strategy="test", accuracy_score=.9, clarity_score=.9, attraction_score=.8, image_match_score=.8) for i in range(5)]
    unit = ViralCopyUnit(semantic_unit_id="u", content_id="c", purpose="opening", full="这是一段完整的中文文章总结，用来验证模板内容绑定不会再依赖旧的固定标题区域和逐幕正文框。", short="这是一段完整的中文文章总结。", micro="中文文章总结。", source_hash=sha256(b"source").hexdigest())
    return ViralCopyPlan(source_article_hash=sha256(b"article").hexdigest(), title_candidates=titles, selected_title_id="t0", final_title="测试系统：可扩展字幕模板", content_units=[unit])


def test_reference_template_registry_and_frozen_bindings():
    selection = select_caption_template()
    plan = build_caption_template_plan(selection, copy_plan=_copy_plan())
    assert get_caption_template(plan.template_id).media_bbox.model_dump() == {"x": 0, "y": 655, "width": 1080, "height": 610}
    assert {item.slot_id for item in plan.global_bindings} == {"title_primary", "title_secondary", "title_tertiary", "summary"}
    validate_caption_template_plan(plan)


def test_unknown_template_and_tampered_binding_are_rejected():
    with pytest.raises(ValueError, match="unknown caption template"):
        get_caption_template("missing")
    plan = build_caption_template_plan(select_caption_template(), copy_plan=_copy_plan())
    changed = plan.global_bindings[0].model_copy(update={"content": "被篡改"})
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_caption_template_plan(plan.model_copy(update={"global_bindings": [changed, *plan.global_bindings[1:]]}))


def test_template_plan_has_no_legacy_fixed_layout_requirement():
    plan = build_caption_template_plan(select_caption_template(), copy_plan=_copy_plan())
    assert plan.template_id == "reference_caption_v1"
    assert all(binding.content for binding in plan.global_bindings)
