import json
import logging
from types import SimpleNamespace

from content_creator.agents.director_chat import _chat_prompt
from content_creator.capabilities.visual_capability_catalog import DIRECTOR_VISUAL_CAPABILITIES, director_capability_guidance, log_intent_adaptation
from content_creator.prompts.director_prompt import director_prompt


def test_catalog_contains_only_supported_director_capabilities():
    names = {item["name"] for items in DIRECTOR_VISUAL_CAPABILITIES.values() for item in items}
    assert {"stretch_reveal", "glass_shatter_transition", "shake_transition", "gaussian_blur_transition"} <= names
    assert "stretch_transition" not in names
    assert "particle_explosion_transition" not in names
    assert "flash_burst_transition" not in names
    assert all(set(item) == {"name", "description", "examples"} for items in DIRECTOR_VISUAL_CAPABILITIES.values() for item in items)


def test_director_prompt_injects_catalog_and_natural_language_rules():
    payload = json.loads(director_prompt([], {}, "cinematic", "guidance"))
    assert payload["available_visual_capabilities"] == DIRECTOR_VISUAL_CAPABILITIES
    rules = "\n".join(payload["rules"])
    assert "film director, not a renderer" in rules
    assert "VisualEvent types" in rules
    assert "Do not invent unsupported effects" in rules
    assert "stretch_transition" in rules


def test_director_chat_prompt_uses_the_same_catalog(tmp_path):
    session = SimpleNamespace(
        style="cinematic",
        project=SimpleNamespace(images=[SimpleNamespace(id="a")]),
        beat_analysis=SimpleNamespace(model_dump=lambda mode="json": {}),
        current_plan=None,
        conversation_history=[],
    )
    payload = json.loads(_chat_prompt(session, "更强烈一点"))
    assert payload["available_visual_capabilities"] == DIRECTOR_VISUAL_CAPABILITIES
    assert "glass_shatter_transition" in director_capability_guidance()
    assert "stretch_transition" in "\n".join(payload["rules"])


def test_unsupported_intent_adaptation_is_debug_only(caplog):
    with caplog.at_level(logging.DEBUG, logger="content_creator.capabilities.visual_capability_catalog"):
        log_intent_adaptation("能量爆炸粒子转场")
    assert "Requested intent: 能量爆炸粒子转场" in caplog.text
    assert "Selected capability family: transition" in caplog.text
