---
name: stretch-motion-design
description: Design silk-smooth stretch reveals for the Video-Assistant Remotion Creative Agent. Use for Chinese direction such as 丝滑拉伸, 液态拉伸, 橡胶弹性, 柔性展开, 果冻感, 拉开进入, or 弹性展开.
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

## Ownership Rule

`stretch_reveal` owns only the entrance of its own image. It is not a
cross-scene transition and must not be given source or target asset IDs.

There is no registered `stretch_transition`. For a scene boundary, choose a
registered transition capability whose visual language matches the direction;
never invent a stretch transition or layer an unregistered transition over an
entrance.
