import json
from pathlib import Path

import pytest

from content_creator.agents.remotion_agent import create_transition_effect_plan
from content_creator.schemas import DirectorPlan, TransitionEffectPlanItem, TransitionEffectType
from content_creator.transitions import (
    TRANSITION_TEMPLATE_REGISTRY,
    TransitionTemplateDefinition,
    enabled_transition_templates,
    get_transition_template,
    validate_transition_template_params,
)


class RecordingProvider:
    model_name = "test-remotion"

    def __init__(self, response: dict | None = None):
        self.response = response or {}
        self.calls = 0

    def complete_json(self, _prompt: str) -> str:
        self.calls += 1
        return json.dumps(self.response)


def transition_plan() -> DirectorPlan:
    return DirectorPlan.model_validate({"timeline": [
        {"asset_id": "image-001", "duration_frames": 60, "transition_intent": {"description": "custom boundary"}},
        {"asset_id": "image-002", "duration_frames": 60},
    ]})


def test_transition_effect_type_is_only_template_infrastructure():
    assert [item.value for item in TransitionEffectType] == ["template_transition"]


def test_production_template_registry_is_empty():
    assert TRANSITION_TEMPLATE_REGISTRY == {}
    assert enabled_transition_templates() == ()


def test_empty_registry_skips_transition_without_calling_llm(caplog):
    provider = RecordingProvider()
    result = create_transition_effect_plan(transition_plan(), provider=provider)
    assert result.transitions == []
    assert provider.calls == 0
    assert "No registered transition templates" in caplog.text


def test_unknown_and_disabled_templates_are_rejected(monkeypatch):
    with pytest.raises(ValueError, match="Unknown transition template"):
        get_transition_template("missing")
    monkeypatch.setitem(TRANSITION_TEMPLATE_REGISTRY, "disabled", TransitionTemplateDefinition(
        id="disabled", description="test only", enabled=False,
    ))
    with pytest.raises(ValueError, match="disabled"):
        get_transition_template("disabled")


def test_registered_test_template_validates_and_serializes(monkeypatch):
    monkeypatch.setitem(TRANSITION_TEMPLATE_REGISTRY, "test_template", TransitionTemplateDefinition(
        id="test_template", description="test only", params={"intensity": {"type": "number", "minimum": 0, "maximum": 1}},
        duration_min=12, duration_max=36, duration_default=18,
    ))
    provider = RecordingProvider({
        "type": "template_transition",
        "duration_frames": 18,
        "params": {"template_id": "test_template", "parameters": {"intensity": 0.7}},
    })
    result = create_transition_effect_plan(transition_plan(), provider=provider)
    assert provider.calls == 1
    assert result.transitions[0].model_dump(mode="json") == {
        "from_asset_id": "image-001", "to_asset_id": "image-002",
        "type": "template_transition", "duration_frames": 18,
        "params": {"template_id": "test_template", "parameters": {"intensity": 0.7}},
        "implementation": "new", "design": result.transitions[0].design,
    }


def test_template_parameter_and_duration_validation(monkeypatch):
    monkeypatch.setitem(TRANSITION_TEMPLATE_REGISTRY, "test_template", TransitionTemplateDefinition(
        id="test_template", description="test only", params={"enabled": {"type": "boolean"}},
        duration_min=10, duration_max=20,
    ))
    assert validate_transition_template_params("test_template", {"enabled": True}, 12) == {"enabled": True}
    with pytest.raises(ValueError, match="Invalid duration"):
        validate_transition_template_params("test_template", {}, 9)
    with pytest.raises(ValueError, match="Unknown parameter"):
        validate_transition_template_params("test_template", {"extra": 1}, 12)


def test_schema_rejects_renderer_implementation_fields():
    with pytest.raises(ValueError):
        TransitionEffectPlanItem.model_validate({
            "from_asset_id": "a", "to_asset_id": "b", "type": "template_transition",
            "duration_frames": 18,
            "params": {"template_id": "test", "component": "UnsafeComponent"},
        })


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_schema_rejects_non_json_numbers(value):
    with pytest.raises(ValueError, match="not JSON-safe"):
        TransitionEffectPlanItem.model_validate({
            "from_asset_id": "a", "to_asset_id": "b", "type": "template_transition",
            "duration_frames": 18,
            "params": {"template_id": "test", "parameters": {"intensity": value}},
        })


def test_remotion_registry_contains_only_template_transition():
    renderer = Path("remotion/src/transitions/TransitionEffectRenderer.tsx").read_text(encoding="utf-8")
    registry = Path("remotion/src/transitions/templates/registry.ts").read_text(encoding="utf-8")
    assert "template_transition: templateTransition" in renderer
    assert "TemplatePresentationRegistry: Record<string, TemplatePresentationComponent> = {}" in registry
