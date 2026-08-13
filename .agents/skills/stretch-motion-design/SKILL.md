---
name: stretch-motion-design
description: Design silk-smooth stretch reveals and stretch transitions for the Video-Assistant Remotion Creative Agent. Use for Chinese direction such as 丝滑拉伸, 液态拉伸, 橡胶弹性, 柔性展开, 果冻感, 拉开进入, or 弹性展开.
---

# Stretch Motion Design

Use only registered VisualEvent types and their documented renderer parameters.
This skill defines the visual language and phase ownership for stretch motion;
do not generate TSX, CSS, component names, or unregistered event types.

## `stretch_reveal`

Use for an image that enters as if a flexible material is pulled open into the
frame. It is an entrance-only effect.

- Required phase: `phase=entrance`
- Motion language: `scaleX`, `scaleY`, elastic deformation, overshoot, and a
  spring settle.
- Prefer a single dominant axis. Use moderate intensity for an elegant reveal;
  reserve stronger overshoot for energetic or playful direction.
- Map `丝滑拉伸`, `液态拉伸`, `橡胶弹性`, `柔性展开`, and `果冻感` to
  `stretch_reveal` when the direction describes one image entering its scene.
- In a single-image entrance context, map `拉开进入` and `弹性展开` to
  `stretch_reveal`.

## `stretch_transition`

Use for a scene boundary where image A stretches and deforms before image B is
revealed. It is transition-only and belongs to the source scene.

- Required phase: `phase=transition`
- Set `source_asset_id` to image A and `target_asset_id` to image B.
- Use this parameter shape when the registered capability accepts it:

```json
{
  "intensity": 0.7,
  "axis": "horizontal",
  "spring": 0.65,
  "blur": 8,
  "easing": "easeOut"
}
```

- `intensity` controls deformation strength; `axis` selects the dominant
  stretch direction; `spring` controls elastic settling; `blur` is motion blur
  during the fastest deformation; `easing` controls the non-spring portion.
- Map `拉开进入` and `弹性展开` to `stretch_transition` when they describe
  image A opening or pulling into image B.

## Ownership Rule

A `stretch_transition` owns the target image reveal. Forbidden: a transition
and target entrance simultaneously at the same boundary. When both are
requested, keep the `stretch_transition` and remove the target entrance.
