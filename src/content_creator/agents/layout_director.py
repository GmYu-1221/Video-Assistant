"""Bounded Layout Director. Model output is optional and always validated."""
from __future__ import annotations
import json

from content_creator.schemas import ImageSemanticProfile, LayoutPlan, SceneLayoutSpec, SceneNarrative
from content_creator.font_registry import public_font_metadata, validate_font_for_role
from content_creator.services.layout.fallback import solve_plan
from content_creator.services.layout.preferences import choose_font_palette
from content_creator.services.layout.validator import validate_scene_layout
from content_creator.services.llm.router import get_agent_provider


def create_layout_plan(items: list[tuple[SceneNarrative, ImageSemanticProfile | None]], global_style: str = "editorial", *, context: dict | None = None, preferences: dict | None = None, feedback_reason: str = "", avoid_fonts: set[str] | None = None) -> tuple[LayoutPlan, dict]:
    provider = get_agent_provider("layout")
    diagnostics = {"model": provider.model_name, "mode": "local_solver", "repairs": 0}
    local_palette = choose_font_palette(context, preferences, avoid=avoid_fonts)
    palette = local_palette
    if provider.model_name != "mock":
        palette_prompt = json.dumps({
            "task": "Choose a coherent typography palette for one Chinese short video. Return JSON only with primary_font_id, accent_font_id and reason. Primary must support caption/body. Accent must support headline. Use registered IDs only, at most two fonts total.",
            "article_context": context or {}, "preference_memory": preferences or {},
            "revision_feedback": feedback_reason, "avoid_when_possible": sorted(avoid_fonts or set()),
            "font_registry": public_font_metadata(),
            "output": {"primary_font_id": "registered-id", "accent_font_id": "registered-id", "reason": "short"},
        }, ensure_ascii=False)
        try:
            raw_palette = provider.complete_json(palette_prompt).strip()
            if raw_palette.startswith("```"):
                raw_palette = raw_palette.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            selected = json.loads(raw_palette)
            primary = selected["primary_font_id"]
            accent = selected.get("accent_font_id") or primary
            validate_font_for_role(primary, "caption")
            validate_font_for_role(accent, "headline")
            palette = [primary] if primary == accent else [primary, accent]
            diagnostics["font_selection_mode"] = "model_success"
            diagnostics["font_reason"] = str(selected.get("reason", ""))[:300]
        except Exception as exc:
            diagnostics["font_selection_mode"] = "local_fallback"
            diagnostics["font_selection_error"] = f"{type(exc).__name__}: {exc}"
    else:
        diagnostics["font_selection_mode"] = "local_fallback"
    diagnostics["font_palette"] = palette
    fallback = solve_plan(items, global_style, context=context, preferences=preferences, avoid_fonts=avoid_fonts, font_palette=palette)
    if provider.model_name == "mock":
        return fallback, diagnostics
    prompt = json.dumps({
        "task": "Design dynamic Chinese subtitle typography for a mobile video. The fixed yellow outlined article title occupies x=60,y=80,width=960,height=280 and must never be covered, repeated, moved, or rewritten. Return only JSON LayoutPlan. Select concrete font_id values only from font_registry. Keep every media block exactly x=0,y=430,width=1080,height=610,fit=contain. If the opening has two frozen contents, place the first as one centered white reference_emphasis summary line in y=360..430 and the second as a centered explanatory block below y=1040. The prominent display headline must come from the selected image pixels; never create an extra display text block for it. Later scenes use explanatory or minimal styling with reduced decoration. You may choose only registered outline, shadow, emphasis_color, letter_spacing, and caption_style_intent tokens from the schema. When copy_density_intent is increase, every frozen content_id is required outside the protected title and media regions. Use at most two font IDs across the video. No English explanatory copy, CSS, font paths, new copy, media changes or transition changes.",
        "canvas": [1080, 1920], "global_style": global_style,
        "font_registry": [font for font in public_font_metadata() if font["id"] in palette], "locked_font_palette": palette, "preference_memory": preferences or {},
        "article_context": context or {}, "revision_feedback": feedback_reason,
        "output_schema": LayoutPlan.model_json_schema(),
        "scenes": [{"narrative": n.model_dump(mode="json"), "image_semantic_profile": p.model_dump(mode="json") if p else None} for n, p in items],
    }, ensure_ascii=False)
    def validate_response(raw: str) -> LayoutPlan:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        candidate = LayoutPlan.model_validate(json.loads(cleaned))
        if any(block.font_id not in palette for scene in candidate.scenes for block in scene.text_blocks):
            raise ValueError("layout response used a font outside the selected palette")
        expected = {n.scene_id for n, _ in items}
        if {scene.scene_id for scene in candidate.scenes} != expected:
            raise ValueError("layout response omitted or invented scene")
        item_by_scene = {n.scene_id: (n, p) for n, p in items}
        hard_issues = []
        for scene in candidate.scenes:
            narrative, profile = item_by_scene[scene.scene_id]
            if len(narrative.contents) > 1:
                required = {content.content_id for content in narrative.contents}
                selected = {block.content_id for block in scene.text_blocks}
                if not required.issubset(selected):
                    raise ValueError("layout response omitted required localized content blocks")
            hard_issues.extend(validate_scene_layout(scene, narrative, profile))
        if hard_issues:
            raise ValueError("layout response failed deterministic validation: " + ",".join(sorted({issue.code for issue in hard_issues})))
        return candidate

    try:
        candidate = validate_response(provider.complete_json(prompt))
        diagnostics["mode"] = "model_success"
        return candidate, diagnostics
    except Exception as first_exc:
        diagnostics["first_error"] = f"{type(first_exc).__name__}: {first_exc}"
        retry_prompt = json.dumps({
            "task": "Return a corrected LayoutPlan JSON object using this valid baseline. Keep all keys and immutable content references, including every text block when copy_density_intent is increase. Preserve the opening reference hierarchy and never create image-headline display copy. You may only change text_blocks geometry, alignment, typography_role, font_id, style_intent, weight, color, outline, shadow, emphasis, emphasis_color, letter_spacing, caption_style_intent, max_lines and variant_id/content_hash pairs already present in the narrative. Keep media_blocks unchanged. Use at most two registered font IDs.",
            "valid_baseline": fallback.model_dump(mode="json"),
            "font_registry": [font for font in public_font_metadata() if font["id"] in palette], "locked_font_palette": palette, "preference_memory": preferences or {},
            "article_context": context or {}, "revision_feedback": feedback_reason,
        }, ensure_ascii=False)
        try:
            candidate = validate_response(provider.complete_json(retry_prompt))
            diagnostics["mode"] = "model_retry_success"
            diagnostics["repairs"] = 1
            return candidate, diagnostics
        except Exception as retry_exc:
            diagnostics["error"] = f"{type(retry_exc).__name__}: {retry_exc}"
            diagnostics["mode"] = "font_model_with_deterministic_layout" if diagnostics.get("font_selection_mode") == "model_success" else "local_solver"
            return fallback, diagnostics


def repair_scene(original: SceneLayoutSpec, narrative: SceneNarrative, profile: ImageSemanticProfile | None, issues: list[dict], global_style: str) -> SceneLayoutSpec:
    # Repair stays local and immutable. A model may improve this later; solver
    # remains the reliable response when a gateway is unavailable.
    return solve_plan([(narrative, profile)], global_style).scenes[0]
