# Usage

```bash
uv sync
cd remotion && pnpm install && cd ..
PYTHONPATH=src python -m content_creator.main --images ./input/images --audio ./input/bgm.wav
```

Use `--width`, `--height`, `--fps`, and `--preview` to customize output. The MP4 is written to `output/projects/<project_id>/render/final.mp4`.
