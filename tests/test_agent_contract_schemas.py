from content_creator.schemas import (
    ArticleImageTaggingDecision, ArticleSelectionDecision, ArticleTranslationBatchDecision,
    AssetSelectionDecision, CandidateVisualAnalysisDecision, CopyFitReviewDecision,
    DirectorDecision, EditorialDecision, ImageHeadlineBatchDecision, ImageHeadlineDecision,
    NormalizedBBoxDecision, ViralCopyDecision,
)
import pytest
from pydantic import ValidationError


STRUCTURED_SCHEMAS = (
    ArticleSelectionDecision, ArticleTranslationBatchDecision,
    CandidateVisualAnalysisDecision, AssetSelectionDecision,
    ArticleImageTaggingDecision, ImageHeadlineBatchDecision,
    EditorialDecision, DirectorDecision, ViralCopyDecision, CopyFitReviewDecision,
)


def _assert_strict_objects(node):
    if isinstance(node, dict):
        if node.get("type") == "object":
            assert node.get("additionalProperties") is False
            assert set(node.get("properties", {})) == set(node.get("required", []))
        for value in node.values():
            _assert_strict_objects(value)
    elif isinstance(node, list):
        for value in node:
            _assert_strict_objects(value)


def test_every_agent_output_schema_is_recursive_strict_and_fully_required():
    for model in STRUCTURED_SCHEMAS:
        _assert_strict_objects(model.model_json_schema(mode="validation"))


def test_director_agent_schema_excludes_python_computed_fields_and_ids():
    schema = DirectorDecision.model_json_schema(mode="validation")
    assert not {"width", "height", "fps", "duration_frames", "start_frame", "end_frame"} & set(schema["properties"])
    scene = schema["$defs"]["DirectorSceneDecision"]["properties"]
    assert "scene_id" not in scene
    assert {"duration_weight", "material_ids", "text_layouts"} <= set(scene)


def test_director_text_layout_contains_semantic_presets_not_python_budgets():
    schema = DirectorDecision.model_json_schema(mode="validation")
    layout = schema["$defs"]["DirectorTextLayoutDecision"]["properties"]
    assert set(layout) == {"field", "typography_profile", "visibility_profile", "hierarchy_level"}
    assert not {"font_size_px", "max_lines", "min_visible_frames", "max_total_units"} & set(layout)


def test_copy_review_targets_real_scene_fields_not_scene_level_character_counts():
    schema = CopyFitReviewDecision.model_json_schema(mode="validation")
    target = schema["$defs"]["CopyFitPageTargetDecision"]["properties"]
    assert set(target) == {"scene_id", "page_index", "field", "action", "max_display_units"}


def test_copy_agent_outputs_semantic_pages_without_ids_or_frame_boundaries():
    schema = ViralCopyDecision.model_json_schema(mode="validation")
    page = schema["$defs"]["ViralCopyPageDecision"]["properties"]
    assert set(page) == {"material_id", "texts", "source_references"}
    assert not {"page_id", "start_frame", "end_frame", "duration_frames"} & set(page)


def test_editorial_ids_are_not_model_output_but_reference_ids_are():
    schema = EditorialDecision.model_json_schema(mode="validation")
    beat = schema["$defs"]["EditorialBeatDecision"]["properties"]
    reference = schema["$defs"]["AgentSourceReference"]["properties"]
    assert "id" not in beat
    assert set(reference) == {"source_id", "paragraph_index"}


def test_translation_limit_applies_to_each_batch():
    paragraphs = ArticleTranslationBatchDecision.model_json_schema()["properties"]["paragraphs"]
    assert paragraphs["minItems"] == 1
    assert paragraphs["maxItems"] == 7


def test_agent_bbox_schema_is_named_normalized_xywh_with_explicit_bounds():
    properties = NormalizedBBoxDecision.model_json_schema()["properties"]
    assert set(properties) == {"x", "y", "width", "height"}
    assert properties["x"]["minimum"] == 0
    assert properties["x"]["maximum"] == 1
    assert properties["width"]["exclusiveMinimum"] == 0
    assert properties["width"]["maximum"] == 1


@pytest.mark.parametrize("bbox", (
    [12, 594, 876, 794],
    {"x": 12, "y": 594, "width": 876, "height": 794},
    {"x": .7, "y": .1, "width": .5, "height": .2},
    {"x": .1, "y": .1, "width": .8, "height": .3, "x2": .9},
))
def test_agent_bbox_rejects_arrays_pixels_out_of_bounds_and_extra_fields(bbox):
    with pytest.raises(ValidationError):
        NormalizedBBoxDecision.model_validate(bbox)


def test_agent_headline_flag_requires_bbox_only_for_prominent_headline():
    base = {
        "image_id": "article-001", "embedded_headline_text": "", "headline_prominence": 0,
        "headline_title_match_score": 0, "headline_readability": 0, "headline_exclusion_reason": "none",
    }
    with pytest.raises(ValidationError, match="must be null"):
        ImageHeadlineDecision.model_validate(base | {
            "contains_prominent_headline": False,
            "headline_bbox": {"x": .1, "y": .1, "width": .8, "height": .2},
        })
    with pytest.raises(ValidationError, match="is required"):
        ImageHeadlineDecision.model_validate(base | {"contains_prominent_headline": True, "headline_bbox": None})
