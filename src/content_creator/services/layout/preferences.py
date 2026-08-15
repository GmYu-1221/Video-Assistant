"""Persistent, local typography preference memory for URL video jobs."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content_creator.font_registry import DEFAULT_FONT_ID, load_font_registry, validate_font_for_role


def article_context(brief: Any) -> dict[str, Any]:
    return {
        "mood": str(getattr(brief, "mood", "informative") or "informative"),
        "topics": list(getattr(brief, "topics", []) or []),
        "title": str(getattr(brief, "title", "") or "")[:240],
    }


class TypographyPreferenceStore:
    def __init__(self, output_root: str | Path):
        self.root = Path(output_root) / "preferences"
        self.root.mkdir(parents=True, exist_ok=True)
        self.history_path = self.root / "typography_feedback.jsonl"
        self.profile_path = self.root / "typography_profile.json"
        self._lock = threading.Lock()

    def records(self) -> list[dict[str, Any]]:
        if not self.history_path.is_file():
            return []
        records = []
        for line in self.history_path.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    records.append(value)
            except json.JSONDecodeError:
                continue
        return records

    def append(self, record: dict[str, Any]) -> dict[str, Any]:
        stored = dict(record)
        stored.setdefault("record_type", "feedback")
        stored.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        with self._lock:
            with self.history_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(stored, ensure_ascii=False) + "\n")
            profile = self._build_profile(self.records())
            self.profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
        return stored

    @staticmethod
    def _build_profile(records: list[dict[str, Any]]) -> dict[str, Any]:
        records = [record for record in records if record.get("record_type", "feedback") == "feedback" and record.get("rating") in {"positive", "negative"}]
        scores: dict[str, float] = {}
        for age, record in enumerate(reversed(records)):
            value = 1.0 if record.get("rating") == "positive" else -1.0
            weight = .97 ** age
            for font_id in set(record.get("font_ids", [])):
                scores[font_id] = scores.get(font_id, 0.0) + value * weight
        return {
            "version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "feedback_count": len(records),
            "font_scores": {key: round(value, 4) for key, value in sorted(scores.items())},
        }

    def summary_for(self, brief: Any) -> dict[str, Any]:
        target = article_context(brief)
        target_terms = {target["mood"].lower(), *(str(item).lower() for item in target["topics"])}
        scores: dict[str, float] = {}
        examples: list[tuple[float, dict[str, Any]]] = []
        records = [record for record in self.records() if record.get("record_type", "feedback") == "feedback" and record.get("rating") in {"positive", "negative"}]
        for age, record in enumerate(reversed(records)):
            context = record.get("context", {})
            terms = {str(context.get("mood", "")).lower(), *(str(item).lower() for item in context.get("topics", []))}
            overlap = len((target_terms - {""}) & (terms - {""}))
            similarity = .55 + min(.45, overlap * .2)
            recency = .97 ** age
            polarity = 1.0 if record.get("rating") == "positive" else -1.0
            contribution = polarity * similarity * recency
            for font_id in set(record.get("font_ids", [])):
                scores[font_id] = scores.get(font_id, 0.0) + contribution
            examples.append((abs(contribution), record))
        examples.sort(key=lambda item: item[0], reverse=True)
        compact = [{
            "rating": record.get("rating"),
            "reason": str(record.get("reason", ""))[:240],
            "font_ids": record.get("font_ids", []),
            "context": record.get("context", {}),
            "copy_density_intent": record.get("copy_density_intent", "preserve"),
        } for _, record in examples[:6]]
        return {"font_scores": {key: round(value, 4) for key, value in scores.items()}, "examples": compact, "feedback_count": len(records)}


def choose_font_palette(context: dict[str, Any] | None = None, preferences: dict[str, Any] | None = None, *, avoid: set[str] | None = None) -> list[str]:
    context = context or {}
    preferences = preferences or {}
    avoid = avoid or set()
    terms = {str(context.get("mood", "")).lower(), *(str(item).lower() for item in context.get("topics", []))}
    preference_scores = preferences.get("font_scores", {})

    def score(font: dict[str, Any], role: str) -> float:
        try:
            validate_font_for_role(font["id"], role)
        except ValueError:
            return -10_000
        metadata = {str(value).lower() for key in ("moods", "styles", "best_for") for value in font.get(key, [])}
        return len((terms - {""}) & metadata) * 1.5 + float(preference_scores.get(font["id"], 0)) * 2 - (2.5 if font["id"] in avoid else 0)

    fonts = list(load_font_registry())
    primary = max(fonts, key=lambda font: (score(font, "caption"), font["id"] == DEFAULT_FONT_ID))["id"]
    accent_candidates = [font for font in fonts if font["id"] != primary]
    accent = max(accent_candidates, key=lambda font: (score(font, "headline"), not font.get("is_artistic")))["id"] if accent_candidates else primary
    return [primary] if accent == primary else [primary, accent]
