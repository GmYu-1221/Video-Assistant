from __future__ import annotations

from hashlib import sha256
import re

from content_creator.font_registry import DEFAULT_FONT_ID, validate_font_for_role
from content_creator.schemas import PersistentTitleSpec, StyleIntent


def build_persistent_title(title: str, font_palette: list[str] | None = None) -> PersistentTitleSpec:
    content = " ".join(title.split()).strip()
    if not content:
        raise ValueError("URL 持久标题不能为空")
    if not re.search(r"[\u3400-\u9fff]", content):
        # Product/repository identifiers may remain untranslated, but the
        # explanatory title itself must be Chinese. Ordinary prose titles are
        # expected to have been translated by Article Localization already.
        repository_match = re.search(r"(?:github\s*-\s*)?[^\s/]+/([A-Za-z0-9_.-]+)\s*$", content, re.I)
        if repository_match:
            content = f"{repository_match.group(1)} 项目介绍"
        else:
            raise ValueError("中文标题本地化失败：顶部标题仍为英文解释文本")
    palette = font_palette or [DEFAULT_FONT_ID]
    font_id = palette[-1]
    try:
        validate_font_for_role(font_id, "headline")
    except ValueError:
        font_id = DEFAULT_FONT_ID
    return PersistentTitleSpec(
        content=content,
        content_hash=sha256(content.encode("utf-8")).hexdigest(),
        font_id=font_id,
        style_intent=StyleIntent.modern_sans,
    )
