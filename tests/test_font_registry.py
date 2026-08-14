from __future__ import annotations

import json
from pathlib import Path

from PIL import ImageFont


REPO_ROOT = Path(__file__).resolve().parents[1]
REMOTION_ROOT = REPO_ROOT / "remotion"
REGISTRY_PATH = REMOTION_ROOT / "src" / "fonts" / "font-registry.json"
ARTISTIC_ALLOWED_ROLES = {"display", "headline", "quote"}


def _registry() -> list[dict]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def test_font_registry_ids_families_and_fallbacks_are_valid() -> None:
    fonts = _registry()
    ids = [font["id"] for font in fonts]
    families = [font["family"] for font in fonts]

    assert len(ids) == len(set(ids))
    assert len(families) == len(set(families))
    assert all(font["fallback_family"] in families for font in fonts)
    assert all(font["weights"] for font in fonts)


def test_registered_cjk_font_assets_and_licenses_exist_and_load() -> None:
    for font in _registry():
        assert font["supports_cjk"] is True
        font_path = REMOTION_ROOT / "public" / font["local_path"]
        license_files = list(font_path.parent.glob("*LICENSE*")) + list(font_path.parent.glob("OFL*"))
        assert font_path.is_file(), font["id"]
        assert font_path.stat().st_size > 100_000, font["id"]
        assert license_files, font["id"]

        loaded = ImageFont.truetype(str(font_path), size=48)
        masks = {bytes(loaded.getmask(character)) for character in "人工智能创作方式"}
        assert len(masks) >= 4, f"CJK glyphs did not render distinctly for {font['id']}"


def test_artistic_fonts_are_not_body_caption_or_metadata_defaults() -> None:
    for font in _registry():
        if not font.get("is_artistic"):
            continue
        assert set(font["roles"]) <= ARTISTIC_ALLOWED_ROLES
        assert {"body", "caption", "metadata"} <= set(font["avoid_for"])


def test_font_showcase_is_registered_and_uses_registry() -> None:
    root = (REMOTION_ROOT / "src" / "Root.tsx").read_text(encoding="utf-8")
    showcase = (REMOTION_ROOT / "src" / "FontShowcase.tsx").read_text(encoding="utf-8")
    loader = (REMOTION_ROOT / "src" / "fonts" / "loadFonts.ts").read_text(encoding="utf-8")

    assert 'id="TypographyFontShowcase"' in root
    assert "FONT_REGISTRY.map" in showcase
    assert "@font-face" not in showcase
    assert "delayRender" in loader
    assert "continueRender" in loader
    assert "new FontFace" in loader
    assert "staticFile(font.local_path)" in loader
