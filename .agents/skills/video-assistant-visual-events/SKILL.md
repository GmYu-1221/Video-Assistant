# Visual Event Architecture

This project expresses every executable visual decision through `visual_events[]`.
`animation` and `transition_effect` are compatibility projections only and must
never be introduced as primary execution fields.

## Event Types

`entrance` controls one image entering its scene. Registered examples include
`drop_reveal_elastic` and `card_flip_reveal`.

`effect` controls a sustained single-scene treatment. Registered examples include
`camera_push` and `light_leak`.

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

## Effect Development Rule

Adding a visual event requires a Python schema, capability registry entry,
TypeScript component, renderer registry entry, automated test, and render
verification. New effects must remain frame-driven and use registered parameters.
