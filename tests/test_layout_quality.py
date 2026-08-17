import pytest
from pydantic import ValidationError

from content_creator.schemas import (CaptionStyleIntent, ContentVariant, ImageSemanticProfile, NarrativeContent, Rect, SceneNarrative, TextBlock, TextOutline, TypographyRole)
from content_creator.services.layout.persistent_title import build_persistent_title
from content_creator.services.layout.fallback import solve_scene
from content_creator.services.layout.validator import validate_persistent_title, validate_scene_layout


def _narrative():
    content = NarrativeContent(semantic_unit_id="unit-copy", content_id="copy", full="人工智能正在改变创作方式", short="人工智能改变创作", micro="AI 创作")
    return SceneNarrative(copy_id="copy-0", scene_id="scene-0", asset_id="asset-0", scene_purpose="opening", contents=[content])


def test_solver_uses_immutable_content_hash_and_no_default_overlay():
    narrative = _narrative()
    scene = solve_scene(narrative, ImageSemanticProfile())
    assert not validate_scene_layout(scene, narrative, ImageSemanticProfile())
    assert scene.media_blocks[0].bbox.model_dump() == {"x": 0, "y": 430, "width": 1080, "height": 610}
    assert scene.media_blocks[0].fit == "contain"
    assert scene.text_blocks[0].content_hash == narrative.contents[0].content_hash(scene.text_blocks[0].variant_id)


def test_validator_rejects_text_over_known_subject_and_undeclared_collision():
    narrative = _narrative()
    scene = solve_scene(narrative, None)
    scene.text_blocks[0] = TextBlock(block_id="primary-copy", content_id="copy", semantic_unit_id="unit-copy", variant_id=ContentVariant.micro, content_hash=narrative.contents[0].content_hash(ContentVariant.micro), bbox=Rect(x=80, y=100, width=800, height=180), typography_role=TypographyRole.headline, max_lines=2)
    profile = ImageSemanticProfile(subject_bbox=Rect(x=0, y=0, width=1080, height=600))
    codes = {issue.code for issue in validate_scene_layout(scene, narrative, profile)}
    assert "subject_occlusion" in codes
    assert "persistent_title_collision" in codes


def test_persistent_title_is_hashed_and_uses_fixed_top_region():
    title = build_persistent_title("人工智能正在改变创作方式")
    assert title.bbox.model_dump() == {"x": 60, "y": 80, "width": 960, "height": 280}
    assert title.typography_role == TypographyRole.headline
    assert title.outline == TextOutline.dark_strong
    assert title.caption_style_intent == CaptionStyleIntent.reference_emphasis
    assert not validate_persistent_title(title)


def test_repository_title_keeps_product_name_but_adds_chinese_explanation():
    title = build_persistent_title("GitHub - deepseek-ai/DeepSeek-V3")
    assert title.content == "DeepSeek-V3 项目介绍"


def test_opening_uses_reference_hierarchy_without_display_overlay():
    summary = NarrativeContent(semantic_unit_id="summary", content_id="summary", full="这是文章摘要说明", short="文章摘要说明", micro="摘要说明")
    body = NarrativeContent(semantic_unit_id="body", content_id="body", full="这是来自文章正文的完整中文解释。", short="来自正文的中文解释。", micro="中文解释")
    narrative = SceneNarrative(copy_id="opening", scene_id="opening", asset_id="image", scene_purpose="opening", contents=[summary, body])
    layout = solve_scene(narrative, ImageSemanticProfile(contains_prominent_headline=True, headline_analysis_status="verified"))
    top, bottom = layout.text_blocks
    assert top.bbox.y >= 360 and top.bbox.y + top.bbox.height <= 430
    assert top.alignment == "center"
    assert top.caption_style_intent == CaptionStyleIntent.reference_emphasis
    assert bottom.bbox.y >= 1040 and bottom.alignment == "center"
    assert bottom.variant_id == ContentVariant.full
    assert all(block.typography_role != TypographyRole.display for block in layout.text_blocks)
    assert not validate_scene_layout(layout, narrative, ImageSemanticProfile(contains_prominent_headline=True, headline_analysis_status="verified"))


def test_text_block_rejects_arbitrary_css_and_unknown_emphasis():
    narrative = _narrative()
    with pytest.raises(ValidationError):
        TextBlock(block_id="copy", content_id="copy", semantic_unit_id="unit-copy", variant_id=ContentVariant.micro, content_hash=narrative.contents[0].content_hash(ContentVariant.micro), bbox=Rect(x=80, y=1100, width=920, height=200), typography_role=TypographyRole.caption, max_lines=2, css={"transform": "scale(2)"})
    scene = solve_scene(narrative, ImageSemanticProfile())
    scene.text_blocks[0] = scene.text_blocks[0].model_copy(update={"emphasis": ["不在字幕里的词"]})
    assert "invalid_emphasis" in {issue.code for issue in validate_scene_layout(scene, narrative, ImageSemanticProfile())}
