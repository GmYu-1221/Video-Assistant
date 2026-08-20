from content_creator.schemas import (
    ArticleImageTaggingDecision, ArticleSelectionDecision, ArticleTranslationBatchDecision,
    AssetSelectionDecision, CandidateVisualAnalysisDecision, CopyFitReviewDecision,
    DirectorDecision, EditorialDecision, ImageHeadlineBatchDecision, ViralCopyDecision,
)


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
    assert {"duration_weight", "material_ids"} <= set(scene)


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
