import json
from types import SimpleNamespace

from content_creator.agents.director_chat import _chat_prompt
from content_creator.capabilities.visual_capability_catalog import DIRECTOR_VISUAL_CAPABILITIES, director_capability_guidance, director_visual_capabilities
from content_creator.prompts.director_prompt import director_prompt
from content_creator.transitions import TRANSITION_TEMPLATE_REGISTRY, TransitionTemplateDefinition


def test_director_exposes_qwen3_8_from_production_registry():
    assert DIRECTOR_VISUAL_CAPABILITIES["transition"] == []
    transitions = director_visual_capabilities()["transition"]
    assert len(transitions) == 1
    assert transitions[0]["name"] == "template_transition"
    assert "模糊" in transitions[0]["description"]
    assert "qwen3_8" in json.loads(director_capability_guidance())["transition"][0]["id"]


def test_director_exposes_no_transition_when_registry_is_empty(monkeypatch):
    monkeypatch.setattr("content_creator.transitions.template_registry.TRANSITION_TEMPLATE_REGISTRY", {})
    assert director_visual_capabilities()["transition"] == []
    assert json.loads(director_capability_guidance())["transition"] == []


def test_director_capabilities_are_generated_from_registry(monkeypatch):
    monkeypatch.setitem(TRANSITION_TEMPLATE_REGISTRY, "test_template", TransitionTemplateDefinition(
        id="test_template", description="test only", examples=("test",),
    ))
    transitions = director_visual_capabilities()["transition"]
    test_template = next(item for item in transitions if item["id"] == "test_template")
    assert test_template["name"] == "template_transition"
    assert test_template["description"] == "test only"


def test_director_prompt_uses_dynamic_catalog():
    payload = json.loads(director_prompt([], {}, "cinematic", "guidance"))
    assert payload["available_visual_capabilities"]["transition"][0]["id"] == "qwen3_8"
    assert payload["available_visual_capabilities"]["entrance"]


def test_director_chat_uses_dynamic_catalog(tmp_path):
    session = SimpleNamespace(
        style="cinematic", project=SimpleNamespace(images=[SimpleNamespace(id="a")]),
        beat_analysis=SimpleNamespace(model_dump=lambda mode="json": {}),
        current_plan=None, conversation_history=[],
    )
    payload = json.loads(_chat_prompt(session, "更强烈一点"))
    assert payload["available_visual_capabilities"]["transition"][0]["id"] == "qwen3_8"
