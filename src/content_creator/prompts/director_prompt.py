import json

from content_creator.capabilities.visual_capability_catalog import DIRECTOR_VISUAL_CAPABILITIES


def director_prompt(images: list[dict], beat_analysis: dict, style: str, remotion_guidance: str = "", capability_catalog: dict | None = None) -> str:
    """Ask an LLM for decisions only, never implementation code or frame positions."""
    instructions = {
        "task": "Create an image video director plan.",
        "output_contract": {
            "timeline": [
                {
                    "asset_id": "input asset id, preserve input order",
                    "duration_frames": "positive integer",
                    "transition_intent": {"scene_id": "input asset id", "description": "optional natural-language description of the transition to the following image", "effects": ["optional descriptive layers"]},
                    "transition_strength": "number from 0 to 1",
                    "motion": "static",
                    "creative_intent": {"scene_id": "input asset id", "description": "director language describing the shot", "movement": "optional movement description", "emotion": "optional emotional tone", "timing": "optional timing description", "style": "cinematic style", "energy": "0 to 1"},
                    "reason": "brief director rationale",
                }
            ]
        },
        "rules": [
            "Return JSON only, without Markdown or commentary.",
            "Return exactly one timeline item for each input image in input order.",
            "Use beat analysis for pacing, but never set timeline start or end frames.",
            "Do not emit TypeScript, React, ffmpeg, crop, cover, scaleX, or scaleY.",
            "Motion must always be static unless a future explicit motion policy changes this contract.",
            "You are a film director, not a component selector. Describe every requested entrance through creative_intent; do not select from an animation or EffectRegistry list.",
            "Words such as 入场、进入、出现、展开、飞入、翻转、推进 describe creative_intent on a scene, not a transition.",
            "Words such as 切换、下一张、两张之间、转场 describe transition_intent on the outgoing scene. Omit transition_intent for the final image.",
            "Describe visual movement, camera behavior, effect layers and timing in natural film language. Never output an implementation, component, TypeScript, CSS, or fixed animation type.",
            "Never select transition.type, an effect type, a Remotion component, or implementation parameters. The Remotion Creative Agent owns those decisions.",
            "You are a film director, not a renderer. Use cinematic language.",
            "The available_visual_capabilities field is an internal feasibility catalog. Do not output its name values.",
            "Do not output component names, VisualEvent types, implementation parameters, or code.",
            "Do not invent unsupported effects. Adapt unavailable requests to the closest supported visual language without rejecting the request.",
            "Generic cinematic or dramatic wording does not automatically add a special effect.",
            "Stretch language describes an entrance into the next shot; never invent stretch_transition.",
        ],
        "style": style,
        "remotion_capability_guidance": remotion_guidance,
        "available_visual_capabilities": capability_catalog or DIRECTOR_VISUAL_CAPABILITIES,
        "images": images,
        "beat_analysis": beat_analysis,
    }
    return json.dumps(instructions, ensure_ascii=False)
