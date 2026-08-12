# Remotion Skill Usage

The official `remotion-dev/skills` package is installed under `.agents/skills/` and remains in the structure produced by `npx skills add remotion-dev/skills`.

The LangGraph Remotion Agent reads the installed best-practices, documentation, markup, and rendering Skill documents. It converts a validated Storyboard into constrained implementation advice: use the existing `Slideshow` component, `contain` image fit, static motion by default, `interpolate`/`spring`/`Easing` for animation, and the existing `TransitionRegistry` for all transitions.

The agent does not generate TypeScript, alter the Remotion project, invoke ffmpeg, or bypass the existing Render Agent. It rejects non-static default motion and never permits `object-fit: cover`, `scaleX`, `scaleY`, `requestAnimationFrame`, or `setTimeout`.

For future LLM use, provide Storyboard JSON to the Director Agent, validate it through Pydantic, then use the Remotion Agent advice to select registered components and transitions. Any advanced transition remains a `TransitionConfig` validated by the existing registry; it is never generated as arbitrary React code.
