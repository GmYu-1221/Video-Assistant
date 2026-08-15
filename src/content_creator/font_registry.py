"""Shared access to the Remotion font registry.

The JSON file is the single source of truth for both Python planning and the
Remotion renderer. Agents only ever see and return registry IDs.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


REGISTRY_PATH = Path(__file__).resolve().parents[2] / "remotion" / "src" / "fonts" / "font-registry.json"
DEFAULT_FONT_ID = "noto-sans-sc"


@lru_cache(maxsize=1)
def load_font_registry() -> tuple[dict[str, Any], ...]:
    records = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("font registry must be a JSON array")
    ids: set[str] = set()
    families: set[str] = set()
    for record in records:
        font_id = record.get("id")
        family = record.get("family")
        if not font_id or font_id in ids:
            raise ValueError(f"invalid or duplicate font id: {font_id}")
        if not family or family in families:
            raise ValueError(f"invalid or duplicate font family: {family}")
        ids.add(font_id)
        families.add(family)
    return tuple(records)


def font_registry_by_id() -> dict[str, dict[str, Any]]:
    return {record["id"]: dict(record) for record in load_font_registry()}


def get_registered_font(font_id: str) -> dict[str, Any]:
    try:
        return font_registry_by_id()[font_id]
    except KeyError as exc:
        raise ValueError(f"unknown registered font: {font_id}") from exc


def validate_font_for_role(font_id: str, role: str) -> dict[str, Any]:
    font = get_registered_font(font_id)
    if role not in font.get("roles", []):
        raise ValueError(f"font {font_id} does not support typography role {role}")
    if font.get("is_artistic") and role in {"body", "caption", "metadata"}:
        raise ValueError(f"artistic font {font_id} cannot be used for {role}")
    if not font.get("supports_cjk"):
        raise ValueError(f"font {font_id} does not support CJK")
    return font


def public_font_metadata() -> list[dict[str, Any]]:
    keys = (
        "id", "family", "weights", "roles", "moods", "styles", "best_for",
        "avoid_for", "supports_cjk", "recommended_max_lines", "is_artistic",
        "license", "license_status",
    )
    return [{key: record.get(key) for key in keys if key in record} for record in load_font_registry()]
