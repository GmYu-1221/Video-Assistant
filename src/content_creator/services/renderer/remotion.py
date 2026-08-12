import json
import subprocess
from pathlib import Path
from content_creator.schemas import VideoProject
from content_creator.services.server import MediaServer


def render_project(project: VideoProject, remotion_dir: str | Path, output_path: str | Path, preview: bool = False) -> Path:
    server = MediaServer(project.output.project_dir)
    base_url = server.start()
    props_path = Path(project.output.project_dir) / ".render_props.json"
    props = project.model_dump(mode="json")
    props["media_base_url"] = base_url
    props_path.write_text(json.dumps(props), encoding="utf-8")
    target = Path(output_path); target.parent.mkdir(parents=True, exist_ok=True)
    try:
        command = ["pnpm", "exec", "remotion", "render", "src/index.ts", "Slideshow", str(target), "--props", str(props_path)]
        if preview:
            command += ["--scale", "0.5"]
        completed = subprocess.run(command, cwd=Path(remotion_dir), check=False)
        if completed.returncode != 0:
            raise RuntimeError(f"Remotion render failed with exit code {completed.returncode}")
        if not target.is_file() or target.stat().st_size == 0:
            raise RuntimeError("Remotion did not produce a non-empty MP4")
        return target
    finally:
        server.close()
