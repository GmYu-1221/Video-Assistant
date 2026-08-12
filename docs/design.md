# Design

The Python Pydantic models are the protocol source. A project is materialized under `output/projects/<id>` with processed images, copied audio, and relative paths in `render_data.json`. A localhost-only MediaServer exposes only `materials/` and `audio/` while Remotion renders. Beat analysis uses librosa and falls back to deterministic BPM timing when a codec or detector cannot provide beats.
