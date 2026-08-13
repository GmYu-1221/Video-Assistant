# Video-Assistant Architecture

## Runtime Flow

```text
User request
  -> Director Agent
  -> DirectorPlan (creative_intent, transition_intent)
  -> one Remotion Creative Agent
     -> AnimationPlan
     -> TransitionEffectPlan
  -> render_data.json
  -> Remotion Renderer
     -> EffectRenderer
     -> TransitionEffectRenderer or legacy TransitionFactory
  -> MP4
```

The Director owns interpretation. It describes scene movement in
`creative_intent` and scene-boundary movement in `transition_intent`. It does
not select Remotion component names, registered effect identifiers, or TSX
parameters.

There is one Remotion Creative Agent, not separate animation or transition
agents. It calls `get_agent_provider("remotion")` once per plan run and uses
the same provider for both plan outputs. It reads the installed project skills
under `.agents/skills/` (`remotion-best-practices`, `remotion-docs`,
`remotion-markup`, and `remotion-render`) and receives the registered
capabilities in its prompt.

## Plan Contracts

`AnimationPlan` attaches a plan to a scene's `animation` field:

```json
{"type":"particle_flip_reveal","duration_frames":24,"params":{"particle_density":240,"rotation_axis":"Y"}}
```

`TransitionEffectPlan` attaches a plan to the outgoing scene's
`transition_effect` field:

```json
{"type":"glass_shatter_transition","duration_frames":18,"params":{"fragment_count":48,"impact_origin":"center","motion_blur":true}}
```

`render_data.json` is the renderer contract. A `timeline` item can contain
both `animation` and `transition_effect`.

## Renderer Priority

`Composition.tsx` applies the following rule at each non-final scene boundary:

1. When `timeline.transition_effect` exists, call `TransitionEffectRenderer`.
2. Otherwise call the legacy `TransitionFactory` with `timeline.transition`.

This keeps `fade`, `crossfade`, `wipe`, `slide`, and all other existing base
transitions compatible. An AI-selected creative transition cannot silently
fall through to the baseline transition.

`TransitionEffectRenderer` is independent from scene `EffectRenderer` and
dispatches through `TransitionEffectRegistry`. The initial registry entry,
`glass_shatter_transition`, renders the outgoing scene as clipped fragment
layers with opacity breakup, displacement, rotation, optional blur, and an
incoming-scene reveal.

## Adding a Scene Animation

1. Implement the TSX effect under `remotion/src/effects/` using frame-driven
   Remotion APIs.
2. Register it in the scene `EffectRegistry`.
3. Add its enum value and capability metadata to the Python animation schema
   and Remotion Creative Agent prompt.
4. Validate its parameters and add an LLM-to-`render_data.json` test.

## Adding a Transition Effect

1. Implement a Remotion transition presentation under
   `remotion/src/transitions/presentations/`.
2. Add a typed `TransitionEffectPlan` entry and register it in
   `TransitionEffectRegistry` in `TransitionEffectRenderer.tsx`.
3. Add the corresponding Python enum and capability metadata in
   `transition_effect_plan.py` and `remotion_agent.py`.
4. Add parameter validation, LLM-plan, render-data, and renderer-dispatch
   tests.

Do not add a new LLM agent for an effect. Extend the existing Remotion Creative
Agent and its capability registry instead.

## Developer Notes

- `TransitionConfig` remains the safe baseline timeline mechanism; it is not a
  Director creative-decision format.
- Unknown LLM-selected registered types are validation errors. Invalid JSON,
  unavailable providers, and network failures use a logged safe fallback.
- The CLI `show` output distinguishes `Transition` (baseline) from `Creative
  Transition` (Director intent), so they are not conflated before rendering.
