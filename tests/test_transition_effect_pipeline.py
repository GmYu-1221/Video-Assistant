import json
from pathlib import Path
import subprocess

import pytest

from content_creator.agents.remotion_agent import create_transition_effect_plan
from content_creator.schemas import DirectorPlan, TransitionEffectPlanItem, TransitionEffectType
from content_creator.transitions import (
    TRANSITION_TEMPLATE_REGISTRY,
    TransitionTemplateDefinition,
    enabled_transition_templates,
    get_transition_template,
    get_transition_template_capabilities,
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


def transition_plan_without_intent() -> DirectorPlan:
    return DirectorPlan.model_validate({"timeline": [
        {"asset_id": "image-001", "duration_frames": 60},
        {"asset_id": "image-002", "duration_frames": 60},
        {"asset_id": "image-003", "duration_frames": 60},
    ]})


def test_transition_effect_type_is_only_template_infrastructure():
    assert [item.value for item in TransitionEffectType] == ["template_transition"]


def test_production_template_registry_contains_qwen3_8():
    assert set(TRANSITION_TEMPLATE_REGISTRY) == {"qwen3_8", "zoom_whip_v2"}
    definition = get_transition_template("qwen3_8")
    assert definition.enabled
    assert definition.duration_min == 12
    assert definition.duration_max == 45
    assert definition.duration_default == 27
    assert enabled_transition_templates() == (definition, get_transition_template("zoom_whip_v2"))
    assert "柔和高级转场" in definition.examples
    assert "玻璃破碎" in definition.avoid_when


def test_empty_registry_skips_transition_without_calling_llm(caplog, monkeypatch):
    monkeypatch.setattr("content_creator.transitions.template_registry.TRANSITION_TEMPLATE_REGISTRY", {})
    provider = RecordingProvider()
    result = create_transition_effect_plan(transition_plan(), provider=provider)
    assert result.transitions == []
    assert provider.calls == 0
    assert "No registered transition templates" in caplog.text


def test_every_image_boundary_gets_qwen_without_transition_intent():
    result = create_transition_effect_plan(transition_plan_without_intent(), provider=RecordingProvider())
    assert len(result.transitions) == 2
    assert [(item.from_asset_id, item.to_asset_id) for item in result.transitions] == [
        ("image-001", "image-002"), ("image-002", "image-003"),
    ]
    assert all(item.params["template_id"] == "qwen3_8" for item in result.transitions)
    assert all(item.design["fallback_reason"] == "no_transition_intent" for item in result.transitions)


def test_unknown_and_disabled_templates_are_rejected(monkeypatch):
    with pytest.raises(ValueError, match="Unknown transition template"):
        get_transition_template("missing")
    monkeypatch.setitem(TRANSITION_TEMPLATE_REGISTRY, "disabled", TransitionTemplateDefinition(
        id="disabled", description="test only", enabled=False,
    ))
    with pytest.raises(ValueError, match="disabled"):
        get_transition_template("disabled")


def test_unregistered_template_is_rejected():
    provider = RecordingProvider({
        "type": "template_transition",
        "duration_frames": 18,
        "params": {"template_id": "missing_template", "parameters": {}},
    })
    result = create_transition_effect_plan(transition_plan(), provider=provider)
    assert provider.calls == 1
    assert len(result.transitions) == 1
    assert result.transitions[0].params["template_id"] == "qwen3_8"
    assert result.transitions[0].design["requested_template_id"] == "missing_template"
    assert result.transitions[0].design["fallback_reason"] == "invalid_response"


def test_zoom_whip_v2_default_contract():
    definition = get_transition_template("zoom_whip_v2")
    assert definition.duration_min == 9
    assert definition.duration_max == 36
    assert definition.duration_default == 20
    assert validate_transition_template_params("zoom_whip_v2", {"zoom": 1.08, "distance": 12, "blur": 10}, 20) == {"zoom": 1.08, "distance": 12, "blur": 10}
    with pytest.raises(ValueError, match="Invalid parameter"):
        validate_transition_template_params("zoom_whip_v2", {"zoom": 1.3}, 20)


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


def test_qwen3_8_capability_and_parameter_contract():
    capability = get_transition_template_capabilities()["qwen3_8"]
    assert set(capability["params"]) == {
        "blur_strength", "float_distance", "recovery_speed", "opacity_start",
    }
    assert capability["duration_frames"] == {"minimum": 12, "maximum": 45, "default": 27}
    parameters = {
        "blur_strength": 0.8,
        "float_distance": 0.55,
        "recovery_speed": 0.7,
        "opacity_start": 0.88,
    }
    assert validate_transition_template_params("qwen3_8", parameters, 24) == parameters
    with pytest.raises(ValueError, match="Invalid parameter"):
        validate_transition_template_params("qwen3_8", {"blur_strength": 1.01}, 24)
    with pytest.raises(ValueError, match="Unknown parameter"):
        validate_transition_template_params("qwen3_8", {"shake": 0.5}, 24)
    with pytest.raises(ValueError, match="Invalid duration"):
        validate_transition_template_params("qwen3_8", parameters, 46)


def test_qwen3_8_serializes_through_template_contract():
    item = TransitionEffectPlanItem.model_validate({
        "from_asset_id": "image-a",
        "to_asset_id": "image-b",
        "type": "template_transition",
        "duration_frames": 27,
        "params": {
            "template_id": "qwen3_8",
            "parameters": {
                "blur_strength": 0.8,
                "float_distance": 0.55,
                "recovery_speed": 0.7,
                "opacity_start": 0.88,
            },
        },
    })
    payload = item.model_dump(mode="json")
    assert payload["type"] == "template_transition"
    assert payload["params"]["template_id"] == "qwen3_8"
    assert "component" not in json.dumps(payload)


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


def test_remotion_registry_dispatches_qwen3_8_through_generic_framework():
    renderer = Path("remotion/src/transitions/TransitionEffectRenderer.tsx").read_text(encoding="utf-8")
    registry = Path("remotion/src/transitions/templates/registry.ts").read_text(encoding="utf-8")
    dispatcher = Path("remotion/src/transitions/templates/TemplateTransition.tsx").read_text(encoding="utf-8")
    assert "template_transition: templateTransition" in renderer
    assert "qwen3_8: Qwen38Transition" in registry
    assert "zoom_whip_v2: ZoomWhipV2Transition" in registry
    assert "TemplatePresentationRegistry[props.passedProps.template_id]" in dispatcher
    assert "qwen3_8" not in dispatcher


def test_zoom_whip_v2_state_animates_both_sides_and_settles():
    state_path = Path("remotion/src/transitions/templates/zoom-whip-v2-state.ts").resolve()
    script = r"""
const fs = require('fs');
const ts = require('./remotion/node_modules/typescript');
const source = fs.readFileSync(process.argv[1], 'utf8');
const output = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}}).outputText;
const loaded = {exports: {}};
new Function('module', 'exports', output)(loaded, loaded.exports);
const p = {zoom: 1.08, distance: 12, blur: 10};
process.stdout.write(JSON.stringify({
  outgoingMid: loaded.exports.getZoomWhipV2State(.68, 'exiting', p),
  outgoingEnd: loaded.exports.getZoomWhipV2State(1, 'exiting', p),
  incomingStart: loaded.exports.getZoomWhipV2State(0, 'entering', p),
  incomingEnd: loaded.exports.getZoomWhipV2State(1, 'entering', p),
}));
"""
    states = json.loads(subprocess.run(["node", "-e", script, str(state_path)], check=True, capture_output=True, text=True).stdout)
    assert states["outgoingMid"]["translateXPct"] == pytest.approx(-12)
    assert states["outgoingMid"]["scale"] == pytest.approx(1.08)
    assert states["outgoingEnd"]["opacity"] == 0
    assert states["incomingStart"]["translateXPct"] == pytest.approx(18.6)
    assert states["incomingStart"]["blurPx"] == pytest.approx(10.5)
    assert states["incomingEnd"] == {"translateXPct": 0, "scale": 1, "blurPx": 0, "opacity": 1}


def test_qwen3_8_state_is_deterministic_and_settles_to_identity():
    state_path = Path("remotion/src/transitions/templates/qwen3-8-state.ts").resolve()
    script = r"""
const fs = require('fs');
const ts = require('./remotion/node_modules/typescript');
const source = fs.readFileSync(process.argv[1], 'utf8');
const output = ts.transpileModule(source, {
  compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022},
}).outputText;
const loaded = {exports: {}};
new Function('module', 'exports', output)(loaded, loaded.exports);
const parameters = {
  blur_strength: 0.8,
  float_distance: 0.55,
  recovery_speed: 0.7,
  opacity_start: 0.88,
};
const initial = loaded.exports.getQwen38TransitionState(0, parameters);
const afterBlur = loaded.exports.getQwen38TransitionState(initial.blurEndProgress, parameters);
const afterPosition = loaded.exports.getQwen38TransitionState(initial.positionEndProgress, parameters);
const final = loaded.exports.getQwen38TransitionState(1, parameters);
process.stdout.write(JSON.stringify({initial, afterBlur, afterPosition, final}));
"""
    result = subprocess.run(
        ["node", "-e", script, str(state_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    states = json.loads(result.stdout)
    assert states["initial"]["blurPx"] > 0
    assert states["initial"]["translateYPct"] > 0
    assert states["initial"]["opacity"] == pytest.approx(0.88)
    assert states["initial"]["blurPx"] == pytest.approx(58)
    assert states["initial"]["translateYPct"] == pytest.approx(1.6)
    assert states["initial"]["blurEndProgress"] == pytest.approx(0.36)
    assert states["initial"]["positionEndProgress"] == pytest.approx(0.82)
    assert states["initial"]["blurEndProgress"] < states["initial"]["positionEndProgress"]
    assert states["afterBlur"]["blurPx"] == 0
    assert states["afterBlur"]["translateYPct"] > 0
    assert states["afterPosition"]["translateYPct"] == 0
    assert states["final"]["blurPx"] == 0
    assert states["final"]["translateYPct"] == 0
    assert states["final"]["opacity"] == 1


def test_qwen3_8_template_has_no_nondeterministic_or_unrequested_motion():
    source = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in (
            "remotion/src/transitions/templates/qwen3-8-state.ts",
            "remotion/src/transitions/templates/qwen3-8.tsx",
        )
    )
    for forbidden in ("Math.random", "Date.now", "setTimeout", "requestAnimationFrame"):
        assert forbidden not in source
    for forbidden_motion in ("rotate", "scale(", "spring("):
        assert forbidden_motion not in source
