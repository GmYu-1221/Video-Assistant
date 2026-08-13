# Visual Event Architecture

This project expresses every executable visual decision through `visual_events[]`.
`animation` and `transition_effect` are compatibility projections only and must
never be introduced as primary execution fields.

## Event Types

`entrance` controls one image entering its scene. Registered examples include
`drop_reveal_elastic` and `card_flip_reveal`.

`camera` controls sustained camera motion such as `camera_push`.

`effect` controls another sustained single-scene treatment. A registered example
is `light_leak`.

`transition` controls the boundary between two images. Every transition event must
include both `source_asset_id` and `target_asset_id`.

```json
{
  "type": "glass_shatter_transition",
  "phase": "transition",
  "source_asset_id": "image-001",
  "target_asset_id": "image-002"
}
```

## Transition Ownership Rule

A transition owns the target image reveal. When a transition targets an asset, do
not create an entrance, fade in, `creative_reveal`, or `particle_flip_reveal` for
that target. Do not layer independent reveals over a transition.

`camera_push` is a sustained source-scene effect and may overlap a transition when
the Director asks to push into a cut; its phase is `camera`. `elastic_blur_reveal`
and `card_flip_reveal` are entrance-only for one image; `card_flip_transition` is
transition-only for two images.

## Glass Shatter Selection

Use `glass_shatter_transition` only when the direction explicitly describes
glass, shattering, fractures, fragments, or an explosion. Do not use it as the
default for an unknown, cinematic, dramatic, strong, premium, or impact cut.
When a strong transition has no specific visual language, prefer the lower-risk
`shake_transition` with restrained intensity and no motion blur.

## Effect Development Rule

Adding a visual event requires a Python schema, capability registry entry,
TypeScript component, renderer registry entry, automated test, and render
verification. New effects must remain frame-driven and use registered parameters.
