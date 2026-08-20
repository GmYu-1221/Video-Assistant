import pytest

from content_creator.schemas import ArticleBrief, LocalizedArticleCopy, VideoCopy
from content_creator.services.article_localization import build_localized_video_copy, validate_localized_display_text
from content_creator.services import article_localization


def test_explanatory_english_is_rejected_but_technical_label_is_allowed() -> None:
    assert validate_localized_display_text(["This is a long explanatory sentence about the article."])
    assert validate_localized_display_text(["Python API"]) == []
    assert validate_localized_display_text(["使用 Python API 获取数据。"]) == []


def test_video_copy_uses_localized_source_and_keeps_existing_chinese_copy() -> None:
    brief = ArticleBrief(url="https://example.com/a", canonical_url="https://example.com/a", title="English title", text="正文内容")
    localized = LocalizedArticleCopy(title="中文标题", summary="中文摘要", paragraphs=["第一段中文说明", "第二段中文说明"])
    copy = build_localized_video_copy(brief, localized, preferred=VideoCopy(headline="中文旧标题", subtitle="中文旧副标题", body="中文旧正文"))
    assert copy.headline == "中文旧标题"
    assert copy.subtitle == "中文旧副标题"
    assert "中文旧正文" in copy.body


def test_video_copy_does_not_accept_english_preferred_copy() -> None:
    brief = ArticleBrief(url="https://example.com/a", canonical_url="https://example.com/a", title="English title", text="正文内容")
    localized = LocalizedArticleCopy(title="中文标题", summary="中文摘要", paragraphs=["中文正文说明"])
    copy = build_localized_video_copy(brief, localized, preferred=VideoCopy(headline="An English explanatory headline"))
    assert copy.headline == "中文标题"


def test_passthrough_normalizes_mixed_github_seo_title() -> None:
    title = (
        "GitHub - aquamarine5/ChaoxingSignFaker: 伪造学习通的签到活动🙋"
        "学习通签到神器。Falsifying the signing activity in only one device · GitHub"
    )
    brief = ArticleBrief(
        url="https://github.com/aquamarine5/ChaoxingSignFaker",
        canonical_url="https://github.com/aquamarine5/ChaoxingSignFaker",
        title=title,
        text="这是已经中文化的项目正文，包含足够信息用于直接通过本地化流程。",
        summary="中文摘要说明。",
    )
    localized, copy, diagnostics = article_localization.localize_article_copy(brief)
    assert localized.title == "ChaoxingSignFaker：伪造学习通的签到活动"
    assert copy.title == localized.title
    assert diagnostics["title_normalized"] is True


def test_passthrough_keeps_normal_chinese_title_unchanged() -> None:
    brief = ArticleBrief(url="https://example.com/a", canonical_url="https://example.com/a", title="人工智能正在改变创作方式", text="这是一段中文正文内容。")
    localized, copy, diagnostics = article_localization.localize_article_copy(brief)
    assert localized.title == brief.title
    assert copy.title == brief.title
    assert diagnostics["title_normalized"] is False


def test_passthrough_excludes_isolated_english_explanation_instead_of_failing(monkeypatch) -> None:
    monkeypatch.setattr(article_localization, "get_agent_provider", lambda *_: pytest.fail("mostly Chinese content must not call the translation model"))
    brief = ArticleBrief(
        url="https://example.com/a", canonical_url="https://example.com/a", title="中文项目说明",
        text="中文正文第一段，完整说明项目目标和使用方法。\nThis paragraph explains an optional integration in plain English.\n中文正文第二段，继续说明执行结果和适用范围。",
        summary="中文摘要。",
    )
    localized, copy, diagnostics = article_localization.localize_article_copy(brief)
    assert "optional integration" not in localized.text
    assert copy.source_paragraph_indices == [0, 2]
    assert diagnostics["excluded_non_chinese_paragraph_indices"] == [1]


def test_batched_translation_retries_only_untranslated_paragraphs(monkeypatch) -> None:
    class Provider:
        model_name = "gemini-3.6-flash"
        calls = 0

        def complete_json(self, prompt: str) -> str:
            self.calls += 1
            if self.calls == 1:
                return '{"title":"中文标题","summary":"中文摘要","paragraphs":[{"source_index":0,"zh_text":"中文段落"},{"source_index":1,"zh_text":"This English sentence remains."}]}'
            return '{"title":"中文标题","summary":"中文摘要","paragraphs":[{"source_index":0,"zh_text":"中文段落"},{"source_index":1,"zh_text":"这是中文翻译。"}]}'

    provider = Provider()
    monkeypatch.setattr(article_localization, "get_agent_provider", lambda _: provider)
    brief = ArticleBrief(url="https://example.com/a", canonical_url="https://example.com/a", title="English title", text="First English paragraph. Second English paragraph.")
    localized, copy, diagnostics = article_localization.localize_article_copy(brief)
    assert localized.text == "中文段落\n这是中文翻译。"
    assert diagnostics["batch_count"] == 1
    assert diagnostics["batches"][0]["attempts"] == 2
