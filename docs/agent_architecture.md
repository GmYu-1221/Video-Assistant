# Agent Architecture

V1.5 adds a local LangGraph orchestration layer around the existing image, audio, timeline, and Remotion services. It does not add a model, database, web service, or cloud dependency.

```text
START -> vision_agent -> director_agent -> remotion_agent -> render_agent -> END
```

`VideoState` carries the validated `VideoProject`, `ImageAnalysis` records, `Storyboard`, Remotion Skill advice, render plan, and errors. The Vision agent uses deterministic Pillow measurements (dimensions, average color, edge density). The Director creates Pydantic `Storyboard` and `ScenePlan` records with `motion=static` and a fade entrance by default. The Remotion Agent reads the installed official Skill documents and validates component, animation, and transition constraints. The Render agent converts those records back to the existing `TimelineItem` and `render_data.json` protocol, then uses the existing audio adapter.

The `LLMProvider` protocol and `MockLLMProvider` are intentionally model-neutral. A future provider can replace director decision generation, but its output must still validate through `Storyboard` and cannot directly emit TypeScript, ffmpeg commands, or arbitrary frame ranges.

Run the workflow with:

```bash
uv run python -m content_creator.main --images ./input/images --audio ./input/bgm.wav --agent-mode
```
