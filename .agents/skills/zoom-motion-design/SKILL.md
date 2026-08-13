---
name: zoom-motion-design
description: Guide the Remotion Creative Agent to select the registered zoom_through_transition for explicit cross-scene pass-through direction.
---

# Zoom Through Motion Design

This is visual-direction guidance for the Remotion Creative Agent. Use only
registered VisualEvent types and documented renderer parameters; do not write
code, component names, or new effect types.

## `zoom_through_transition`

`zoom_through_transition` is a cinematic cross-scene pass-through: the current
image rapidly expands as the camera passes through it, then the next image
emerges after the pass-through. It is a scene-boundary transition, not a
single-scene zoom.

Use it for:

- camera passing through the current image into the next scene
- moving through an image, screen, frame, or visual surface to enter the next shot
- explicit cinematic push-through language such as `穿过画面`, `穿越图片`,
  `推进穿过`, `放大穿越`, `zoom through`, or `push through`

Do not use it for:

- a normal zoom in or simple magnification
- a single-image entrance
- `camera_push`
- `stretch_reveal`
- static image movement

## Distinctions

### `camera_push`

`camera_push` is sustained camera motion within one scene. It does not replace
the current image with another image. Use it for `缓慢推进`, `镜头推进`, or a
Ken Burns-style push; do not turn it into `zoom_through_transition`.

### `stretch_reveal`

`stretch_reveal` is an entrance-only deformation for one image entering its
own scene. It does not cross an image boundary. Use it for flexible, elastic,
or silk-like image arrival, not pass-through replacement.

### `card_flip_transition`

`card_flip_transition` rotates the outgoing image as a card or page. It does
not simulate the camera moving through the image. Use Zoom Through when depth
comes from forward travel into the next scene, not 3D card rotation.

## Parameter Guidance

Use only the registered parameter shape:

```json
{
  "intensity": 0.75,
  "direction": "center"
}
```

- `intensity` ranges from `0` to `1`; use moderate values for cinematic travel
  and stronger values for deliberate, energetic pass-throughs.
- `direction` is `center`, `left`, `right`, `top`, or `bottom`; it selects the
  pass-through focal point. Use `center` when the direction gives no focal side.

## Transition Ownership

This effect must be emitted as exactly a cross-scene VisualEvent:

- `type="zoom_through_transition"`
- `phase="transition"`
- `source_asset_id` is the outgoing image
- `target_asset_id` is the next image

The transition owns the target image reveal. Do not add a competing entrance,
fade, `creative_reveal`, `stretch_reveal`, or other reveal to the target image
at the same boundary.

## Registered Type Boundary

Never invent effect names. In particular, do not emit:

- `zoom_blur_transition`
- `cinematic_zoom_effect`
- `tunnel_transition`

When the direction is only a normal zoom, a camera push, or a static image
treatment, choose the applicable registered capability instead of adapting it
into an unregistered zoom transition.
