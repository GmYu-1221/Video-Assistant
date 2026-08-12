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
        ],
        "style": style,
        "images": images,
        "beat_analysis": beat_analysis,
    }
    return json.dumps(instructions, ensure_ascii=False)
