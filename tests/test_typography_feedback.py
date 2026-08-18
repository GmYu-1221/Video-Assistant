from pathlib import Path

import pytest

from content_creator.font_registry import get_registered_font, load_font_registry
from content_creator.schemas import ArticleBrief, ContentVariant, CopyDensityIntent, ImageSemanticProfile, LayoutIssue, NarrativeContent, Rect, RenderedLayoutValidationResult, SceneNarrative, TextBlock, TypographyRole
from content_creator.services.layout.preferences import TypographyPreferenceStore
from content_creator.services.layout.fallback import solve_scene
from content_creator.services.layout.qa import validate_rendered_layout
from content_creator.services.layout.revision import _repair_rendered_overflow
from content_creator.services.layout.copy_density import detect_copy_density_intent, expand_project_narratives
from content_creator.services.layout.validator import validate_scene_layout


def narrative():
    content = NarrativeContent(semantic_unit_id="unit", content_id="copy", full="人工智能正在改变创作方式", short="人工智能改变创作", micro="AI 创作")
    return SceneNarrative(copy_id="copy-0", scene_id="scene-0", asset_id="asset-0", scene_purpose="opening", contents=[content])


def test_registry_files_and_fallbacks_exist():
    root = Path(__file__).parents[1] / "remotion" / "public"
    records = load_font_registry()
    assert len({font["id"] for font in records}) == len(records)
    assert len({font["family"] for font in records}) == len(records)
    families = {font["family"] for font in records}
    for font in records:
        assert (root / font["local_path"]).is_file()
        assert font["fallback_family"] in families
        assert get_registered_font(font["id"])


def test_unknown_and_artistic_font_constraints_are_rejected():
    base = solve_scene(narrative(), ImageSemanticProfile())
    with pytest.raises(ValueError):
        TextBlock.model_validate(base.text_blocks[0].model_dump() | {"font_id": "does-not-exist"})
    with pytest.raises(ValueError):
        TextBlock(block_id="body", content_id="copy", semantic_unit_id="unit", content_hash=narrative().contents[0].content_hash(ContentVariant.full), bbox=Rect(x=60, y=1100, width=900, height=300), typography_role=TypographyRole.body, font_id="ma-shan-zheng", max_lines=2)


def test_preference_memory_is_recent_and_contextual(tmp_path):
    store = TypographyPreferenceStore(tmp_path)
    store.append({"rating": "positive", "font_ids": ["lxgw-wenkai"], "reason": "温暖", "context": {"mood": "warm", "topics": ["story"]}})
    store.append({"rating": "negative", "font_ids": ["source-han-serif"], "reason": "太严肃", "context": {"mood": "warm", "topics": ["story"]}})
    summary = store.summary_for(type("Brief", (), {"mood": "warm", "topics": ["story"], "title": "故事"})())
    assert summary["feedback_count"] == 2
    assert summary["font_scores"]["lxgw-wenkai"] > summary["font_scores"]["source-han-serif"]
    assert (tmp_path / "preferences" / "typography_feedback.jsonl").is_file()
    assert (tmp_path / "preferences" / "typography_profile.json").is_file()


def test_solver_always_emits_registered_font_id():
    spec = solve_scene(narrative(), ImageSemanticProfile(), font_palette=["source-han-serif", "zcool-qingke-huangyou"])
    assert spec.text_blocks[0].font_id in {"source-han-serif", "zcool-qingke-huangyou"}


def test_chromium_wraps_long_url_and_renderer_uses_the_same_rules():
    value = "Hacker News 讨论：https://news.ycombinator.com/item?id=49285244&source=video-assistant"
    content = NarrativeContent(semantic_unit_id="unit", content_id="copy", full=value, short=value, micro=value)
    scene_narrative = SceneNarrative(copy_id="copy-0", scene_id="scene-0", asset_id="asset-0", scene_purpose="evidence", contents=[content])
    spec = solve_scene(scene_narrative, ImageSemanticProfile(), font_palette=["source-han-serif"])
    spec.text_blocks[0] = spec.text_blocks[0].model_copy(update={
            "bbox": Rect(x=80, y=1335, width=920, height=348),
        "font_id": "source-han-serif",
        "variant_id": ContentVariant.micro,
        "content_hash": content.content_hash(ContentVariant.micro),
    })

    rendered = validate_rendered_layout(spec, scene_narrative, Path(__file__).parents[1] / "remotion" / "public")

    assert rendered.passed
    assert rendered.blocks["primary-copy"]["scrollWidth"] <= rendered.blocks["primary-copy"]["clientWidth"] + 1
    renderer = (Path(__file__).parents[1] / "remotion" / "src" / "layout" / "TextBlockRenderer.tsx").read_text(encoding="utf-8")
    assert "overflowWrap:'anywhere'" in renderer
    assert "wordBreak:'break-word'" in renderer


def test_overflow_repair_expands_width_inside_safe_margin_and_shortens_in_stages():
    scene_narrative = narrative()
    spec = solve_scene(scene_narrative, ImageSemanticProfile(), font_palette=["source-han-serif"])
    block = spec.text_blocks[0].model_copy(update={
        "bbox": Rect(x=80, y=1200, width=920, height=300),
        "font_id": "source-han-serif",
        "variant_id": ContentVariant.full,
        "content_hash": scene_narrative.contents[0].content_hash(ContentVariant.full),
    })
    spec = spec.model_copy(update={"text_blocks": [block]})
    horizontal = RenderedLayoutValidationResult(
        scene_id=spec.scene_id,
        blocks={"primary-copy": {"scrollWidth": 959, "clientWidth": 920, "scrollHeight": 300, "clientHeight": 300}},
        issues=[LayoutIssue(code="rendered_overflow", block_id="primary-copy", message="overflow")],
        passed=False,
    )

    widened = _repair_rendered_overflow(spec, scene_narrative, horizontal)

    assert widened.text_blocks[0].bbox.x == 60
    assert widened.text_blocks[0].bbox.width == 960
    assert widened.text_blocks[0].variant_id == ContentVariant.short
    assert widened.media_blocks == spec.media_blocks

    vertical = RenderedLayoutValidationResult(
        scene_id=spec.scene_id,
        blocks={"primary-copy": {"scrollWidth": 960, "clientWidth": 960, "scrollHeight": 900, "clientHeight": 300}},
        issues=[LayoutIssue(code="rendered_overflow", block_id="primary-copy", message="overflow")],
        passed=False,
    )
    shortened = _repair_rendered_overflow(widened, scene_narrative, vertical)
    assert shortened.text_blocks[0].variant_id == ContentVariant.micro
    assert shortened.text_blocks[0].content_hash == scene_narrative.contents[0].content_hash(ContentVariant.micro)


def test_copy_density_feedback_expands_article_grounded_narratives_without_duplicate_variants(tmp_path):
    from content_creator.schemas import AudioConfig, BoundaryAction, ImageAsset, LayoutAction, ResolvedTimelineItem, TimelineItem, TransitionConfig, VideoCopy, VideoOutput, VideoProject
    from content_creator.services.layout.revision import project_copy_metrics

    content = NarrativeContent(semantic_unit_id="unit", content_id="primary", full="标题内容足够长用于测试", short="标题内容", micro="标题")
    scene = SceneNarrative(copy_id="copy", scene_id="scene", asset_id="image", scene_purpose="explanation", contents=[content])
    layout = solve_scene(scene, ImageSemanticProfile())
    state = ResolvedTimelineItem(segment_id="segment", scene_id="scene", start_frame=0, end_frame=30, duration_frames=30, resolved_media_id="image", resolved_copy_id="copy", resolved_layout_id=layout.layout_id, visibility="visible", boundary_action=BoundaryAction.continuous, requested_layout_action=LayoutAction.replace, resolved_layout_action=LayoutAction.replace, transition=TransitionConfig())
    project = VideoProject(project_id="density", fps=30, width=1080, height=1920, images=[ImageAsset(id="image", filename="image.jpg", relative_path="image.jpg", width=1080, height=610, semantic_profile=ImageSemanticProfile())], audio=AudioConfig(path="audio.wav", duration=1, sample_rate=44100), timeline=[TimelineItem(asset_id="image", start_frame=0, end_frame=30, duration_frames=30, transition=TransitionConfig(), narrative=scene, layout=layout, resolved_state=state)], output=VideoOutput(project_dir=str(tmp_path), render_data=str(tmp_path / "render_data.json"), final_video=str(tmp_path / "final.mp4")), video_copy=VideoCopy())
    brief = ArticleBrief(url="https://example.com/a", title="人工智能正在改变创作方式的标题", text="第一条事实包含足够的正文信息用于字幕扩展。第二条事实说明了结果和影响。第三条事实提供补充背景。", summary="文章摘要补充。", requested_url="https://example.com/a", canonical_url="https://example.com/a", effective_base_url="https://example.com/a")

    assert detect_copy_density_intent("文案太少，内容太空，上下都有元素") == CopyDensityIntent.increase
    expanded, diagnostics = expand_project_narratives(project, brief, CopyDensityIntent.increase)
    narrative = expanded["segment"]

    assert diagnostics["after_candidate_character_count"] > diagnostics["before_character_count"]
    assert len(narrative.contents) == 1
    assert all(len(item.full) > len(item.short) > len(item.micro) for item in narrative.contents)
    assert narrative.contents[0].source_paragraph_indices == [0, 1]
    assert narrative.contents[0].source_index == 0
    assert "第一条事实" in narrative.contents[0].full
    assert "第二条事实" in narrative.contents[0].full
    assert "第三条事实" not in narrative.contents[0].full
    plan = solve_scene(narrative, ImageSemanticProfile(), font_palette=["source-han-serif", "noto-sans-sc"], copy_density_intent=CopyDensityIntent.increase)
    assert len(plan.text_blocks) == 1
    assert not validate_scene_layout(plan, narrative, None)
    assert project_copy_metrics(project)["block_count"] == 1
