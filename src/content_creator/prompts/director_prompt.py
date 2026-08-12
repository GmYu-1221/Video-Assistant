import json


def director_prompt(images: list[dict], beat_analysis: dict, style: str, remotion_guidance: str = "") -> str:
    """Ask an LLM for decisions only, never implementation code or frame positions."""
    instructions = {
        "task": "Create an image video director plan.",
        "output_contract": {
            "timeline": [
                {
                    "asset_id": "input asset id, preserve input order",
                    "duration_frames": "positive integer",
                    "transition": {"type": "registered transition type", "duration_frames": "positive integer"},
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
            "Words such as 切换、下一张、两张之间、转场 describe the transition between scenes.",
            "Describe visual movement, camera behavior, effect layers and timing in natural film language. Never output an implementation, component, TypeScript, CSS, or fixed animation type.",
            "Opening transition: use fade or crossfade.",
            "Normal beats: use crossfade, push, or digital_wipe.",
            "Strong beats: use whip, glitch, flash, or zoom_cut.",
            "Climax beats: use iris or white_flash.",
            "Do not use the same transition more than twice consecutively.",
            "For 8 or more images, use at least 4 different transition types.",
            "Fade must be less than 30% of total transitions.",
            "Use beat_strengths to map low beats to fade/crossfade, medium beats to push/digital_wipe, and high beats to whip/glitch/flash.",
            "Use fast durations: fade/crossfade 8, push 6, whip/glitch 5, flash 3, iris 8 frames. Never default to 15 frames.",
        ],
        "style": style,
        "remotion_capability_guidance": remotion_guidance,
        "images": images,
        "beat_analysis": beat_analysis,
    }
    return json.dumps(instructions, ensure_ascii=False)
