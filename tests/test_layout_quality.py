from content_creator.schemas import (ContentVariant, ImageSemanticProfile, NarrativeContent, Rect, SceneNarrative, TextBlock, TypographyRole)
from content_creator.services.layout.fallback import solve_scene
from content_creator.services.layout.validator import validate_scene_layout


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
    assert "subject_occlusion" in {issue.code for issue in validate_scene_layout(scene, narrative, profile)}
