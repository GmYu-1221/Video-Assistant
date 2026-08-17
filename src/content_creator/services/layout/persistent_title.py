from __future__ import annotations

from hashlib import sha256
import re

from PIL import ImageFont

from content_creator.font_registry import DEFAULT_FONT_ID, REGISTRY_PATH, get_registered_font, validate_font_for_role
from content_creator.schemas import PersistentTitleSpec, StyleIntent
from content_creator.services.title_normalization import article_title_candidates


def _font_id(font_palette: list[str] | None) -> str:
    palette = font_palette or [DEFAULT_FONT_ID]
    font_id = palette[-1]
    try:
        validate_font_for_role(font_id, "headline")
    except ValueError:
        font_id = DEFAULT_FONT_ID
    return font_id


def persistent_title_preflight_fits(content: str, font_id: str) -> bool:
    """Cheap font-aware line estimate; Chromium remains the final authority."""
    try:
        font = get_registered_font(font_id)
        path = REGISTRY_PATH.parents[2] / "public" / font["local_path"]
        face = ImageFont.truetype(str(path), 54)
        available_width = 954  # 960px box minus the 3px outline on each side.
        lines = 1
        width = 0.0
        for char in content:
            if char == "\n":
                lines += 1
                width = 0.0
                continue
            char_width = float(face.getlength(char))
            if width and width + char_width > available_width:
                lines += 1
                width = char_width
            else:
                width += char_width
        return lines <= 3 and lines * 54 * 1.28 <= 280
    except Exception:
        # A preflight failure must not replace the browser's real measurement.
        return True


def build_persistent_title_candidates(title: str, font_palette: list[str] | None = None) -> list[PersistentTitleSpec]:
    candidates = article_title_candidates(title)
    content = candidates[0] if candidates else " ".join(title.split()).strip()
    if not content:
        raise ValueError("URL 持久标题不能为空")
    if not any(re.search(r"[\u3400-\u9fff]", candidate) for candidate in candidates or [content]):
        # Product/repository identifiers may remain untranslated, but the
        # explanatory title itself must be Chinese. Ordinary prose titles are
        # expected to have been translated by Article Localization already.
        repository_match = re.search(r"(?:github\s*-\s*)?[^\s/]+/([A-Za-z0-9_.-]+)\s*$", content, re.I)
        if repository_match:
            content = f"{repository_match.group(1)} 项目介绍"
            candidates = [content]
        else:
            raise ValueError("中文标题本地化失败：顶部标题仍为英文解释文本")
    font_id = _font_id(font_palette)
    return [PersistentTitleSpec(content=candidate, content_hash=sha256(candidate.encode("utf-8")).hexdigest(), font_id=font_id, style_intent=StyleIntent.modern_sans) for candidate in candidates]


def build_persistent_title(title: str, font_palette: list[str] | None = None) -> PersistentTitleSpec:
    return build_persistent_title_candidates(title, font_palette)[0]
