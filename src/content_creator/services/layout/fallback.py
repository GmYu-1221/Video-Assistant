from __future__ import annotations

from content_creator.font_registry import DEFAULT_FONT_ID, validate_font_for_role
from content_creator.schemas import (BackgroundTreatment, ContentVariant, CopyDensityIntent, ImageSemanticProfile, LayoutPlan, MediaBlock, NarrativeContent, OverlayPolicy, Rect, SceneLayoutSpec, SceneNarrative, StyleIntent, TextBlock, TypographyRole)
from content_creator.services.layout.preferences import choose_font_palette


def _free_regions(profile: ImageSemanticProfile | None) -> list[Rect]:
    # Known safe areas are authoritative. Unknown is intentionally not treated
    # as centered subject data or an empty safe region.
    if profile and profile.safe_text_regions:
        return sorted(profile.safe_text_regions, key=lambda r: r.width * r.height, reverse=True)
    if profile and profile.subject_bbox:
        subject = profile.subject_bbox
        lower_y = min(1740, subject.y + subject.height + 30)
        candidates = [
            Rect(x=60, y=60, width=960, height=max(180, subject.y - 90)),
            Rect(x=60, y=lower_y, width=960, height=max(120, 1860 - lower_y)),
        ]
        return sorted(candidates, key=lambda r: r.width * r.height, reverse=True)
    return [Rect(x=60, y=60, width=960, height=360), Rect(x=60, y=1500, width=960, height=360)]


def solve_scene(narrative: SceneNarrative, profile: ImageSemanticProfile | None, *, global_style: str = "editorial", font_palette: list[str] | None = None, copy_density_intent: CopyDensityIntent = CopyDensityIntent.preserve) -> SceneLayoutSpec:
    dense = bool(profile and (profile.contains_text or profile.is_screenshot or profile.is_data_chart))
    # URL video contract: media geometry is fixed. Layout freedom belongs to
    # typography only, and `contain` guarantees that the full image is visible.
    media_bbox = Rect(x=0, y=430, width=1080, height=610)
    first = narrative.contents[0]
    text_role = TypographyRole.caption if dense else TypographyRole.headline
    palette = font_palette or [DEFAULT_FONT_ID]
    preferred_font = palette[-1] if text_role in {TypographyRole.display, TypographyRole.headline, TypographyRole.quote} else palette[0]
    try:
        validate_font_for_role(preferred_font, text_role.value)
    except ValueError:
        preferred_font = palette[0]
        try:
            validate_font_for_role(preferred_font, text_role.value)
        except ValueError:
            preferred_font = DEFAULT_FONT_ID
    purpose = narrative.scene_purpose
    if purpose in {"explanation", "conclusion", "quote"}:
        text_bbox = Rect(x=80, y=1120, width=920, height=420 if dense else 300)
    elif purpose in {"evidence", "detail"}:
        text_bbox = Rect(x=80, y=1120, width=920, height=300)
    else:
        text_bbox = Rect(x=60, y=80, width=960, height=280)
    first_variant = ContentVariant.micro if copy_density_intent == CopyDensityIntent.reduce else ContentVariant.short if len(narrative.contents) > 1 or dense else ContentVariant.micro
    text_blocks = [TextBlock(block_id="primary-copy", content_id=first.content_id, semantic_unit_id=first.semantic_unit_id, variant_id=first_variant, content_hash=first.content_hash(first_variant), bbox=text_bbox if len(narrative.contents) == 1 else Rect(x=60, y=80, width=960, height=280), alignment="left", typography_role=text_role, font_id=preferred_font, style_intent=StyleIntent.readable_serif if global_style == "editorial" else StyleIntent.modern_sans, weight="bold", color="#FFFFFF", max_lines=3 if dense or len(narrative.contents) > 1 else 2)]
    if len(narrative.contents) > 1 and copy_density_intent != CopyDensityIntent.reduce:
        support = narrative.contents[1]
        support_font = palette[0]
        try:
            validate_font_for_role(support_font, TypographyRole.body.value)
        except ValueError:
            support_font = DEFAULT_FONT_ID
        text_blocks.append(TextBlock(block_id="support-copy", content_id=support.content_id, semantic_unit_id=support.semantic_unit_id, variant_id=ContentVariant.full, content_hash=support.content_hash(ContentVariant.full), bbox=Rect(x=80, y=1120, width=920, height=560), alignment="left", typography_role=TypographyRole.body, font_id=support_font, style_intent=StyleIntent.readable_serif if global_style == "editorial" else StyleIntent.modern_sans, weight="regular", color="#FFFFFF", max_lines=8))
    return SceneLayoutSpec(
        layout_id=f"layout-{narrative.scene_id}",
        scene_id=narrative.scene_id,
        background=BackgroundTreatment(color="#101214", overlay_opacity=0),
        media_blocks=[MediaBlock(block_id="media", asset_id=narrative.asset_id, bbox=media_bbox, fit="contain", full_bleed=False)],
        text_blocks=text_blocks,
        overlay_policy=OverlayPolicy(allowed_pairs=[]), minimal_scene=not dense and len(text_blocks) == 1,
    )


def solve_plan(items: list[tuple[SceneNarrative, ImageSemanticProfile | None]], global_style: str = "editorial", *, context: dict | None = None, preferences: dict | None = None, avoid_fonts: set[str] | None = None, font_palette: list[str] | None = None) -> LayoutPlan:
    palette = font_palette or choose_font_palette(context, preferences, avoid=avoid_fonts)
    intent = CopyDensityIntent((context or {}).get("copy_density_intent", CopyDensityIntent.preserve.value))
    return LayoutPlan(global_style=global_style, scenes=[solve_scene(narrative, profile, global_style=global_style, font_palette=palette, copy_density_intent=intent) for narrative, profile in items])
