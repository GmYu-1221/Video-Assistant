import json


def director_prompt(images: list[dict], beat_analysis: dict, style: str) -> str:
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
                    "animation_intent": {"type": "optional director intent only", "direction": "optional", "speed": "slow|medium|fast", "duration_frames": "positive integer", "energy": "0 to 1", "camera_motion": "optional", "visual_effects": [], "description": "optional"},
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
            "Use animation_intent only for an explicit entrance or visual direction. Example: 3d_card_flip with back_to_front direction. Never emit TSX, React, CSS, or component source.",
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
        "images": images,
        "beat_analysis": beat_analysis,
    }
    return json.dumps(instructions, ensure_ascii=False)
