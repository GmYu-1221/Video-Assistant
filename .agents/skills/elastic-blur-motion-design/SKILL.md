---
name: elastic-blur-motion-design
description: Design weighted elastic image entrances with a brief lens blur for the Video-Assistant Remotion Creative Agent.
---

# Elastic Blur Motion Design

This is visual-direction guidance for the Remotion Creative Agent. Use only the
registered `elastic_blur_reveal` VisualEvent and its documented parameters. Do
not generate TSX, CSS, component names, or new effect types.

## `elastic_blur_reveal`

Use when one image enters its own scene with physical weight: a brief horizontal
stretch, vertical compression, slight opacity reduction, and light lens blur
recover through a spring-like settle. A small overshoot is allowed, but the
image must finish completely still and sharp.

- Required phase: `phase=entrance`
- Duration: 18-36 frames
- Parameters: `intensity` (0-1), `blur_px` (0-24), `opacity` (0-1)
- After the event: `scale=1`, `rotate=0`, `translate=0`, `opacity=1`, `blur=0`

Use for direction such as:

- 图片像有重量一样弹入
- 物理弹性入场，带轻微镜头虚化
- 压缩后回弹并恢复清晰

## Boundaries

This is an entrance for one image, not a scene transition. It does not use
`source_asset_id` or `target_asset_id`, must not be emitted with `phase=effect`,
and must not cover a target reveal owned by a transition.

Do not use it for ordinary zoom, `camera_push`, `stretch_reveal`, blur
transitions, or any cross-scene replacement. Never invent or emit:

- `elastic_blur_transition`
- `stretch_transition`
- `cinematic_elastic_effect`
- `weighted_blur_reveal`

When a transition targets the image, keep the transition as the owner of that
reveal and omit this entrance event.
