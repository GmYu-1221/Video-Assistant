from __future__ import annotations

import re
from hashlib import sha256

from content_creator.schemas import CaptionTemplateManifest, CaptionTemplatePlan, CaptionTemplateSelection, CaptionTemplateSlot, CaptionTemplateSlotBinding, ViralCopyPlan
from content_creator.schemas import Rect, TypographyRole


_REFERENCE = CaptionTemplateManifest(
    template_id="reference_caption_v1",
    version="1.0",
    description="三行全局标题、居中主图和全片固定底部总结。",
    media_bbox=Rect(x=0, y=655, width=1080, height=610),
    slots=[
        CaptionTemplateSlot(slot_id="title_primary", scope="global", bbox=Rect(x=60, y=92, width=960, height=96), typography_roles=[TypographyRole.display, TypographyRole.headline], max_lines=1, alignments=["center"], allowed_style_tokens=["yellow", "dark_outline", "strong_shadow"], z_index=31),
        CaptionTemplateSlot(slot_id="title_secondary", scope="global", bbox=Rect(x=60, y=210, width=960, height=108), typography_roles=[TypographyRole.display, TypographyRole.headline], max_lines=2, alignments=["center"], allowed_style_tokens=["yellow", "dark_outline", "strong_shadow"], z_index=31),
        CaptionTemplateSlot(slot_id="title_tertiary", scope="global", bbox=Rect(x=60, y=352, width=960, height=84), typography_roles=[TypographyRole.headline, TypographyRole.body], max_lines=1, alignments=["center"], allowed_style_tokens=["white", "dark_outline", "strong_shadow"], z_index=31),
        CaptionTemplateSlot(slot_id="summary", scope="global", bbox=Rect(x=80, y=1325, width=920, height=500), typography_roles=[TypographyRole.body, TypographyRole.caption], max_lines=8, alignments=["center"], allowed_style_tokens=["white", "soft_shadow"], z_index=31),
    ],
    protected_regions=[Rect(x=0, y=655, width=1080, height=610)],
    visual_qa=["global_slots_stable", "media_centered_contain", "summary_is_one_paragraph"],
)

_REGISTRY = {_REFERENCE.template_id: _REFERENCE}


def list_caption_templates(*, enabled_only: bool = True) -> list[CaptionTemplateManifest]:
    return [manifest for manifest in _REGISTRY.values() if manifest.enabled or not enabled_only]


def get_caption_template(template_id: str) -> CaptionTemplateManifest:
    try:
        manifest = _REGISTRY[template_id]
    except KeyError as exc:
        raise ValueError(f"unknown caption template: {template_id}") from exc
    if not manifest.enabled:
        raise ValueError(f"caption template is disabled: {template_id}")
    return manifest


def validate_caption_template_plan(plan: CaptionTemplatePlan) -> None:
    manifest = get_caption_template(plan.template_id)
    if plan.template_version != manifest.version or plan.selection.template_id != plan.template_id:
        raise ValueError("caption template plan identity mismatch")
    expected = {slot.slot_id for slot in manifest.slots if slot.scope == "global" and slot.required}
    actual = {binding.slot_id for binding in plan.global_bindings}
    if actual != expected:
        raise ValueError(f"caption template global slots mismatch: expected {sorted(expected)}, received {sorted(actual)}")
    if len(actual) != len(plan.global_bindings):
        raise ValueError("caption template contains duplicate global slot bindings")
    known_global = {slot.slot_id: slot for slot in manifest.slots if slot.scope == "global"}
    for binding in plan.global_bindings:
        if binding.slot_id not in known_global:
            raise ValueError(f"unknown caption template global slot: {binding.slot_id}")
        if binding.content_hash != sha256(binding.content.encode("utf-8")).hexdigest():
            raise ValueError(f"caption template content hash mismatch: {binding.slot_id}")
    known_scene = {slot.slot_id for slot in manifest.slots if slot.scope == "scene"}
    for binding in plan.scene_bindings:
        if binding.slot_id not in known_scene:
            raise ValueError(f"unknown caption template scene slot: {binding.slot_id}")
        if binding.content_hash != sha256(binding.content.encode("utf-8")).hexdigest():
            raise ValueError(f"caption template content hash mismatch: {binding.slot_id}")
    summary = next(binding.content for binding in plan.global_bindings if binding.slot_id == "summary")
    if len(summary) > 140 or "\n" in summary:
        raise ValueError("reference caption summary must be one paragraph no longer than 140 characters")


def select_caption_template(*, model_template_id: str | None = None, reason: str = "") -> CaptionTemplateSelection:
    if model_template_id and model_template_id in _REGISTRY and _REGISTRY[model_template_id].enabled:
        return CaptionTemplateSelection(template_id=model_template_id, selection_mode="agent", reason=reason)
    manifest = list_caption_templates()[0]
    return CaptionTemplateSelection(template_id=manifest.template_id, selection_mode="deterministic_fallback", reason=reason or "唯一已启用模板")


def _binding(slot_id: str, content: str) -> CaptionTemplateSlotBinding:
    digest = sha256(content.encode("utf-8")).hexdigest()
    return CaptionTemplateSlotBinding(slot_id=slot_id, content_id=f"template-{slot_id}", semantic_unit_id=f"template-{slot_id}", variant_id="full", content=content, content_hash=digest)


def _title_lines(title: str) -> tuple[str, str]:
    parts = [part.strip() for part in re.split(r"[：:，,。！？!?]", title, maxsplit=1) if part.strip()]
    if len(parts) > 1:
        return parts[0], parts[1]
    midpoint = max(1, min(len(title) - 1, len(title) // 2))
    return title[:midpoint].strip(), title[midpoint:].strip()


def _global_bindings(plan: ViralCopyPlan) -> list[CaptionTemplateSlotBinding]:
    if len(plan.caption_title_lines) == 3:
        primary, secondary, tertiary = plan.caption_title_lines
    else:
        primary, secondary = _title_lines(plan.final_title)
        tertiary = plan.content_units[0].short
    summary_parts: list[str] = []
    length = 0
    for unit in plan.content_units:
        value = re.sub(r"\s+", " ", unit.full).strip()
        if not value or value in summary_parts:
            continue
        if length >= 80 and length + len(value) > 140:
            break
        summary_parts.append(value)
        length += len(value)
        if length >= 100:
            break
    summary = (plan.global_summary or "".join(summary_parts))[:139].rstrip("，,；;：:")
    if not summary.endswith(("。", "！", "？", ".", "!", "?")):
        summary += "。"
    return [_binding("title_primary", primary), _binding("title_secondary", secondary), _binding("title_tertiary", tertiary), _binding("summary", summary)]


def build_caption_template_plan(selection: CaptionTemplateSelection, *, copy_plan: ViralCopyPlan | None = None, bindings=None, style_tokens=None) -> CaptionTemplatePlan:
    manifest = get_caption_template(selection.template_id)
    resolved_bindings = list(bindings or (_global_bindings(copy_plan) if copy_plan else []))
    plan = CaptionTemplatePlan(template_id=manifest.template_id, template_version=manifest.version, selection=selection, global_bindings=resolved_bindings, style_tokens=dict(style_tokens or {}))
    if resolved_bindings:
        validate_caption_template_plan(plan)
    return plan
