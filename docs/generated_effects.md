# Generated Effects

Creative mode effects are implementation plans generated from structured `animation_intent` values and registered under `remotion/src/effects/`.

## stretch_reveal

- Director description: image stretches and enters from a requested direction.
- Implementation: `new`
- File: `remotion/src/effects/StretchReveal.tsx`
- Registry: `remotion/src/effects/index.tsx`
- APIs: `useCurrentFrame`, `useVideoConfig`, `spring`, `interpolate`
- Parameters: `direction`, `strength`, `blurPx`, `duration_frames`
- Safety: transform and filter are removed after the entrance duration; the wrapped `ImageFrame` remains contain-based.

Creative mode is enabled with `RENDER_AGENT_MODE=creative`. Unknown intents use this safe generated effect plan instead of a fade fallback. Arbitrary source generation is not performed at runtime.
