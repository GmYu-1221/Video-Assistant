from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .layout import Rect, TypographyRole


class CaptionTemplateSlot(BaseModel):
    slot_id: str = Field(min_length=1, max_length=80)
    scope: Literal["global", "scene"] = "scene"
    required: bool = True
    bbox: Rect
    typography_roles: list[TypographyRole] = Field(min_length=1, max_length=7)
    max_lines: int = Field(ge=1, le=8)
    alignments: list[Literal["left", "center", "right"]] = Field(default_factory=lambda: ["left"], min_length=1)
    allowed_style_tokens: list[str] = Field(default_factory=list, max_length=24)
    z_index: int = Field(default=10, ge=0, le=40)


class CaptionTemplateManifest(BaseModel):
    template_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9_]+$")
    version: str = Field(min_length=1, max_length=20)
    description: str = Field(default="", max_length=500)
    canvas_width: Literal[1080] = 1080
    canvas_height: Literal[1920] = 1920
    media_bbox: Rect = Field(default_factory=lambda: Rect(x=0, y=430, width=1080, height=610))
    media_fit: Literal["contain"] = "contain"
    slots: list[CaptionTemplateSlot] = Field(min_length=1, max_length=16)
    protected_regions: list[Rect] = Field(default_factory=list, max_length=8)
    visual_qa: list[str] = Field(default_factory=list, max_length=16)
    enabled: bool = True

    @model_validator(mode="after")
    def unique_slots(self) -> "CaptionTemplateManifest":
        if len({slot.slot_id for slot in self.slots}) != len(self.slots):
            raise ValueError("caption template slot IDs must be unique")
        return self


class CaptionTemplateSelection(BaseModel):
    template_id: str
    selection_mode: Literal["agent", "deterministic_fallback"]
    reason: str = Field(default="", max_length=500)


class CaptionTemplateSlotBinding(BaseModel):
    slot_id: str
    content_id: str
    semantic_unit_id: str
    variant_id: str
    content: str = Field(min_length=1, max_length=800)
    content_hash: str = Field(min_length=64, max_length=64)


class CaptionTemplatePlan(BaseModel):
    template_id: str
    template_version: str
    selection: CaptionTemplateSelection
    global_bindings: list[CaptionTemplateSlotBinding] = Field(default_factory=list)
    scene_bindings: list[CaptionTemplateSlotBinding] = Field(default_factory=list)
    style_tokens: dict[str, str] = Field(default_factory=dict)
