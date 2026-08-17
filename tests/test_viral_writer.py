import json
from hashlib import sha256
from pathlib import Path

from content_creator.agents import viral_writer
from content_creator.schemas import (
    ArticleBrief, BoundaryAction, CopyAction, DirectorTimelineAction,
    ImageSemanticProfile, LayoutAction, StateAction, TransitionConfig,
)
from content_creator.services.timeline_state import resolve_timeline
from content_creator.services.layout.revision import VERSION_ARTIFACTS


def brief():
    return ArticleBrief(
        url="https://example.com/article", canonical_url="https://example.com/article",
        title="人工智能如何改变创作", summary="工具会变化，创作判断才是核心。",
        text="人工智能正在改变内容创作的方式，也让更多人能够快速表达自己的想法。\n真正重要的不是追逐工具，而是建立清晰的判断和表达能力。",
    )


def response_payload(article, *, english=False, ungrounded_number=False):
    title_texts = [
        "人工智能正在改写创作方式", "一分钟看懂人工智能创作", "创作者真正需要关注什么",
        "工具变了，创作核心没变", "人工智能时代如何保持判断力",
    ]
    if english:
        title_texts[0] = "This is a completely English explanatory headline"
    full = "人工智能降低了表达门槛，但清晰的判断仍然决定作品质量。"
    if ungrounded_number:
        full = "人工智能让创作效率提升了99%。"
    return {
        "platform": "douyin_short_video",
        "source_article_hash": sha256(article.text.encode()).hexdigest(),
        "title_candidates": [{
            "candidate_id": f"title-{index}", "text": text, "strategy": "清晰表达",
            "accuracy_score": .9, "clarity_score": .9, "attraction_score": .8,
            "image_match_score": .7, "source_paragraph_indices": [0],
        } for index, text in enumerate(title_texts)],
        "selected_title_id": "title-0", "final_title": title_texts[0],
        "content_units": [
            {
                "semantic_unit_id": "viral-opening", "content_id": "viral-opening-copy", "purpose": "opening",
                "full": full, "short": "人工智能降低表达门槛，判断仍决定质量。", "micro": "判断决定创作质量",
                "origin": "creative", "source_paragraph_indices": [0], "source_hash": "",
            },
            {
                "semantic_unit_id": "viral-explanation", "content_id": "viral-explanation-copy", "purpose": "explanation",
                "full": "真正重要的不是追逐工具，而是建立清晰、稳定并且可复用的表达能力。",
                "short": "重要的是建立稳定的表达能力。", "micro": "建立表达能力",
                "origin": "source_rewrite", "source_paragraph_indices": [1], "source_hash": "",
            },
        ],
    }


class Provider:
    model_name = "test-model"

    def __init__(self, payload):
        self.payload = payload

    def complete_json(self, _prompt):
        return json.dumps(self.payload, ensure_ascii=False)


def test_project_skill_is_pinned_and_complete():
    root = Path(__file__).resolve().parents[1]
    source = json.loads((root / ".agents/skills/viral-writer/SOURCE.json").read_text())
    assert source["commit"] == "1c76f891fb928ceb22fd101044d100d759f8cee5"
    assert "MIT" in source["license_status"]
    assert "11个内容洞见维度" in viral_writer.load_viral_writer_skill()
    assert "viral_copy_plan.json" in VERSION_ARTIFACTS


def test_mock_provider_builds_five_titles_and_gradient_units(monkeypatch):
    monkeypatch.setattr(viral_writer, "get_agent_provider", lambda _name: type("Mock", (), {"model_name": "mock"})())
    plan, diagnostics = viral_writer.create_viral_copy_plan(brief(), [], 1)
    assert len(plan.title_candidates) == 5
    assert len({item.text for item in plan.title_candidates}) == 5
    assert all(len(unit.full) > len(unit.short) > len(unit.micro) for unit in plan.content_units)
    assert diagnostics["mode"] == "deterministic_fallback"


def test_model_plan_is_selected_and_frozen_without_rewriting(monkeypatch):
    article = brief()
    monkeypatch.setattr(viral_writer, "get_agent_provider", lambda _name: Provider(response_payload(article)))
    plan, diagnostics = viral_writer.create_viral_copy_plan(article, [], 1)
    assert diagnostics["mode"] == "model_success"
    assert plan.final_title == "人工智能正在改写创作方式"
    action = DirectorTimelineAction(
        segment_id="segment-000", scene_id="scene-000", duration_frames=90,
        media_action=StateAction.replace, copy_action=CopyAction.replace,
        layout_action=LayoutAction.replace, boundary_action=BoundaryAction.continuous,
        replacement_media_id="image", narrative_source_ids=["viral:opening"], transition=TransitionConfig(),
    )
    bundle = resolve_timeline(
        [action], {"image": ImageSemanticProfile()}, title=plan.final_title,
        body=article.text, summary=article.summary, copy_plan=plan,
    )
    contents = bundle.segment_narratives["segment-000"].contents
    assert [item.semantic_unit_id for item in contents] == ["viral-opening", "viral-explanation"]
    assert contents[0].full == plan.content_units[0].full
    assert contents[0].source_hash == plan.content_units[0].source_hash


def test_invalid_english_or_ungrounded_fact_falls_back(monkeypatch):
    article = brief()
    for payload in (response_payload(article, english=True), response_payload(article, ungrounded_number=True)):
        monkeypatch.setattr(viral_writer, "get_agent_provider", lambda _name, payload=payload: Provider(payload))
        plan, diagnostics = viral_writer.create_viral_copy_plan(article, [], 1)
        assert diagnostics["mode"] == "deterministic_fallback"
        assert diagnostics["error"]
        assert plan.final_title == article.title


def test_malformed_model_response_falls_back(monkeypatch):
    monkeypatch.setattr(viral_writer, "get_agent_provider", lambda _name: Provider("not-json"))
    plan, diagnostics = viral_writer.create_viral_copy_plan(brief(), [], 1)
    assert diagnostics["mode"] == "deterministic_fallback"
    assert len(plan.title_candidates) == 5


def test_fallback_skips_mixed_sentence_whose_micro_variant_becomes_english():
    article = ArticleBrief(
        url="https://example.com/technical", canonical_url="https://example.com/technical",
        title="中文技术说明", summary="这是文章摘要。",
        text=(
            "这是第一段中文说明，介绍项目的核心目标和主要用途。\n"
            "parameters 与 output.schema 的规范。\n"
            "这是中间的关键证据，说明配置变更会在下一次请求生效。\n"
            "这是最终结论，提醒使用者以官方最新文档为准。"
        ),
    )
    plan = viral_writer._fallback_plan(article, 2)
    values = [value for unit in plan.content_units for value in (unit.full, unit.short, unit.micro)]
    assert viral_writer.validate_localized_display_text(values) == []
    assert all("parameters 与 output." not in value for value in values)
    assert plan.content_units[-1].purpose == "conclusion"
