# Remotion Motion Design

Runtime guidance for the Remotion Creative Agent. Choose only registered visual
events and their documented parameters; never describe or generate TSX.

## Image Animation Guidance

- Prefer spring-driven arrivals over opacity-only fades. A strong entrance combines
  opacity, translation or rotation, and scale, then settles.
- Use `drop_reveal_elastic` for gravity-like movement from a direction with a
  spring settle. Use a flip only when spatial rotation is explicit in the intent.
- Use `particle_flip_reveal` for particle assembly plus rotation, not for a simple
  image arrival. Use `creative_reveal` only when the intent does not justify a
  more specific registered event.
- Use `camera_push` for sustained cinematic emphasis, not as an entrance.
- A still image should have purposeful camera movement or a brief entrance, but
  do not stack independent reveals on a transition-owned target.

## Cinematic Motion Guidance

- Fast impact: short duration, spring overshoot, controlled blur, then settle.
- Drop: directional displacement followed by elastic settling.
- Glass shatter: center or edge impact, fragment spread, depth, motion blur, and
  reveal of the target image behind fragments.
- Entrance and transition durations must respect the registered capability range.
- Favor a clear motion beat and a short hold instead of unrelated simultaneous
  effects.

## Decision Rules

Use motion semantics, the Director intent, and capability descriptions together.
Do not select an event from keywords alone. Never emit unregistered effects,
component names, CSS, or implementation instructions.
