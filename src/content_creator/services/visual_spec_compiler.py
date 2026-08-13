"""Expand high-level transition presets into deterministic animation tracks."""
from __future__ import annotations

from content_creator.schemas.visual_spec import (
    AnimatableProperty, AnimationTrack, EasingType, Keyframe,
    TransitionPreset, TransitionSpec,
)


def _track(target: str, property: AnimatableProperty, values: list[tuple[int, float, EasingType]]) -> AnimationTrack:
    return AnimationTrack(target=target, property=property, keyframes=[Keyframe(frame=f, value=v, easing=e) for f, v, e in values])


def expand_transition_preset(transition: TransitionSpec, incoming_layer_id: str) -> TransitionSpec:
    if transition.preset is None or transition.tracks:
        return transition
    duration = transition.duration_frames
    params = transition.params
    if transition.preset == TransitionPreset.clean_cut:
        tracks = []
    elif transition.preset == TransitionPreset.crossfade:
        tracks = [_track(incoming_layer_id, AnimatableProperty.opacity, [(0, 0, EasingType.linear), (duration, 1, EasingType.linear)])]
    elif transition.preset == TransitionPreset.white_flash:
        peak = min(1.0, max(0.0, float(params.get("flash_peak", 0.95))))
        peak_frame = max(1, min(duration - 1, int(params.get("flash_peak_frame", max(1, duration // 3)))))
        tracks = [_track("transition-overlay", AnimatableProperty.overlay_opacity, [(0, 0, EasingType.linear), (peak_frame, peak, EasingType.linear), (duration, 0, EasingType.linear)])]
    elif transition.preset == TransitionPreset.flash_zoom_blur:
        settle = max(1, min(duration, int(params.get("settle_frames", min(8, duration)))))
        peak_frame = max(1, min(duration - 1, int(params.get("flash_peak_frame", max(1, duration // 3)))))
        scale = min(3.0, max(0.5, float(params.get("incoming_scale", 1.14))))
        blur = min(80.0, max(0.0, float(params.get("blur_px", 24))))
        peak = min(1.0, max(0.0, float(params.get("flash_peak", 0.95))))
        tracks = [
            _track(incoming_layer_id, AnimatableProperty.opacity, [(0, 0.35, EasingType.linear), (settle, 1, EasingType.ease_out_cubic)]),
            _track(incoming_layer_id, AnimatableProperty.scale, [(0, scale, EasingType.linear), (settle, 1, EasingType.ease_out_cubic)]),
            _track(incoming_layer_id, AnimatableProperty.blur, [(0, blur, EasingType.linear), (settle, 0, EasingType.ease_out_cubic)]),
            _track("transition-overlay", AnimatableProperty.overlay_opacity, [(0, 0, EasingType.linear), (peak_frame, peak, EasingType.linear), (duration, 0, EasingType.linear)]),
        ]
    else:
        tracks = []
    return transition.model_copy(update={"tracks": tracks})
