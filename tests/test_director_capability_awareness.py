import json
from types import SimpleNamespace

from content_creator.agents.director_chat import _chat_prompt
from content_creator.capabilities.visual_capability_catalog import DIRECTOR_VISUAL_CAPABILITIES, director_capability_guidance, director_visual_capabilities
from content_creator.prompts.director_prompt import director_prompt
from content_creator.transitions import TRANSITION_TEMPLATE_REGISTRY, TransitionTemplateDefinition


def test_director_exposes_no_transition_when_registry_is_empty():
    assert DIRECTOR_VISUAL_CAPABILITIES["transition"] == []
    assert director_visual_capabilities()["transition"] == []
    assert json.loads(director_capability_guidance())["transition"] == []


def test_director_capabilities_are_generated_from_registry(monkeypatch):
    monkeypatch.setitem(TRANSITION_TEMPLATE_REGISTRY, "test_template", TransitionTemplateDefinition(
        id="test_template", description="test only", examples=("test",),
    ))
    transitions = director_visual_capabilities()["transition"]
    assert transitions[0]["name"] == "template_transition"
    assert transitions[0]["description"] == "test only"


def test_director_prompt_uses_dynamic_catalog():
    payload = json.loads(director_prompt([], {}, "cinematic", "guidance"))
    assert payload["available_visual_capabilities"]["transition"] == []
    assert payload["available_visual_capabilities"]["entrance"]


def test_director_chat_uses_dynamic_catalog(tmp_path):
    session = SimpleNamespace(
        style="cinematic", project=SimpleNamespace(images=[SimpleNamespace(id="a")]),
        beat_analysis=SimpleNamespace(model_dump=lambda mode="json": {}),
        current_plan=None, conversation_history=[],
    )
    payload = json.loads(_chat_prompt(session, "更强烈一点"))
    assert payload["available_visual_capabilities"]["transition"] == []
