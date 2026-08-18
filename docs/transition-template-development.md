# Transition Template Development

All previous creative scene-boundary transitions have been removed. The
production Python and Remotion template registries are intentionally empty.
Baseline timeline transitions remain separate and continue to control timing
and scene overlap.

To add a custom creative transition:

1. Create a presentation in `remotion/src/transitions/templates/`.
2. Register it in `TemplatePresentationRegistry`.
3. Register the matching metadata and parameter contract in Python's
   `TRANSITION_TEMPLATE_REGISTRY`.
4. Add template-specific schema, Agent, serialization, and renderer tests.
5. Run the targeted and full Python test suites.
6. Run `pnpm run build` in `remotion/`.

The Agent selects only `template_transition` plus a registered `template_id`.
It cannot provide components, code, paths, imports, CSS, or renderer details.
