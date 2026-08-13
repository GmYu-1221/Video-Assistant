"""Versioned, renderer-safe visual composition protocol."""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class LayoutPreset(str, Enum):
    fullscreen = "fullscreen"
    center_stage = "center_stage"


class LayerType(str, Enum):
    image = "image"
    text = "text"
    solid = "solid"
    overlay = "overlay"


class EasingType(str, Enum):
    linear = "linear"
    ease_out_cubic = "easeOutCubic"
    ease_in_out_quad = "easeInOutQuad"


class AnimatableProperty(str, Enum):
    opacity = "opacity"
    scale = "transform.scale"
    translate_x = "transform.translateX"
    translate_y = "transform.translateY"
    blur = "filter.blur"
    overlay_opacity = "overlay.opacity"


class TransitionPreset(str, Enum):
    clean_cut = "clean_cut"
    crossfade = "crossfade"
    white_flash = "white_flash"
    flash_zoom_blur = "flash_zoom_blur"


PROPERTY_LIMITS: dict[AnimatableProperty, tuple[float, float]] = {
    AnimatableProperty.opacity: (0, 1),
    AnimatableProperty.scale: (0.5, 3),
    AnimatableProperty.translate_x: (-200, 200),
    AnimatableProperty.translate_y: (-200, 200),
    AnimatableProperty.blur: (0, 80),
    AnimatableProperty.overlay_opacity: (0, 1),
}


class Keyframe(BaseModel):
    frame: int = Field(ge=0)
    value: float
    easing: EasingType = EasingType.linear


class AnimationTrack(BaseModel):
    target: str | None = None
    property: AnimatableProperty
    keyframes: list[Keyframe] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_keyframes(self) -> "AnimationTrack":
        frames = [keyframe.frame for keyframe in self.keyframes]
        if frames != sorted(frames) or len(set(frames)) != len(frames):
            raise ValueError("keyframes must be strictly ordered by frame")
        low, high = PROPERTY_LIMITS[self.property]
        if any(keyframe.value < low or keyframe.value > high for keyframe in self.keyframes):
            raise ValueError(f"{self.property.value} values must be between {low} and {high}")
        return self


class Region(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    overflow: Literal["visible", "hidden"] = "visible"


class LayoutSpec(BaseModel):
    preset: LayoutPreset
    regions: dict[str, Region] = Field(min_length=1)


class LayerSource(BaseModel):
    asset_id: str | None = None
    content: str | None = None


class VisualLayer(BaseModel):
    id: str = Field(min_length=1)
    type: LayerType
    region: str = Field(min_length=1)
    source: LayerSource = Field(default_factory=LayerSource)
    style: dict[str, Any] = Field(default_factory=dict)
    tracks: list[AnimationTrack] = Field(default_factory=list)


class SceneSpec(BaseModel):
    id: str = Field(min_length=1)
    start_frame: int = Field(ge=0)
    duration_frames: int = Field(gt=0)
    layers: list[VisualLayer] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_tracks_are_local(self) -> "SceneSpec":
        for layer in self.layers:
            for track in layer.tracks:
                if track.keyframes[-1].frame > self.duration_frames:
                    raise ValueError(f"track on {layer.id} exceeds scene duration")
        return self


class TransitionSpec(BaseModel):
    id: str = Field(min_length=1)
    from_scene: str = Field(min_length=1)
    to_scene: str = Field(min_length=1)
    start_frame: int = Field(ge=0)
    duration_frames: int = Field(gt=0)
    preset: TransitionPreset | None = None
    params: dict[str, float | str] = Field(default_factory=dict)
    tracks: list[AnimationTrack] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_tracks_are_local(self) -> "TransitionSpec":
        for track in self.tracks:
            if track.keyframes[-1].frame > self.duration_frames:
                raise ValueError("transition track exceeds transition duration")
        return self


class CompositionSpec(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: int = Field(gt=0)
    duration_frames: int = Field(gt=0)
    background: str = "#000000"


class VisualSpec(BaseModel):
    version: Literal["2.0"] = "2.0"
    composition: CompositionSpec
    layout: LayoutSpec
    persistent_layers: list[VisualLayer] = Field(default_factory=list)
    scenes: list[SceneSpec] = Field(min_length=1)
    transitions: list[TransitionSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> "VisualSpec":
        regions = set(self.layout.regions)
        scene_ids = {scene.id for scene in self.scenes}
        layer_ids = {layer.id for layer in self.persistent_layers}
        for scene in self.scenes:
            layer_ids.update(layer.id for layer in scene.layers)
            if scene.start_frame + scene.duration_frames > self.composition.duration_frames:
                raise ValueError(f"scene {scene.id} exceeds composition duration")
            if any(layer.region not in regions for layer in scene.layers):
                raise ValueError(f"scene {scene.id} references an unknown region")
        if any(layer.region not in regions for layer in self.persistent_layers):
            raise ValueError("persistent layer references an unknown region")
        for transition in self.transitions:
            if transition.from_scene not in scene_ids or transition.to_scene not in scene_ids:
                raise ValueError("transition references an unknown scene")
            if transition.start_frame + transition.duration_frames > self.composition.duration_frames:
                raise ValueError("transition exceeds composition duration")
            if any(track.target and track.target not in layer_ids and track.target != "transition-overlay" for track in transition.tracks):
                raise ValueError("transition track references an unknown layer")
        return self
