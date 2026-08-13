import json
import subprocess
from pathlib import Path
from content_creator.schemas import VideoProject
from content_creator.services.server import MediaServer
from typing import Callable

ProgressCallback = Callable[[str], None]


def render_project(project: VideoProject, remotion_dir: str | Path, output_path: str | Path, preview: bool = False, on_progress: ProgressCallback | None = None) -> Path:
    if on_progress:
        on_progress("渲染器|正在准备预览..." if preview else "渲染器|正式渲染开始...")
    server = MediaServer(project.output.project_dir)
    base_url = server.start()
    props_path = Path(project.output.project_dir) / ".render_props.json"
    props = project.model_dump(mode="json")
    props["media_base_url"] = base_url
    props_path.write_text(json.dumps(props), encoding="utf-8")
    target = Path(output_path); target.parent.mkdir(parents=True, exist_ok=True)
    try:
        if on_progress:
            on_progress("渲染器|正在打包 Remotion 项目...")
        command = ["pnpm", "exec", "remotion", "render", "src/index.ts", "Slideshow", str(target), "--props", str(props_path)]
        if preview:
            if on_progress:
                on_progress("渲染器|正在渲染预览帧...")
            command += ["--scale", "0.5"]
        elif on_progress:
            on_progress("渲染器|正在渲染并编码视频...")
        completed = subprocess.run(command, cwd=Path(remotion_dir), check=False)
        if completed.returncode != 0:
            raise RuntimeError(f"Remotion render failed with exit code {completed.returncode}")
        if not target.is_file() or target.stat().st_size == 0:
            raise RuntimeError("Remotion did not produce a non-empty MP4")
        if on_progress:
            on_progress("完成|预览已完成" if preview else "完成|视频渲染已完成")
        return target
    finally:
        server.close()
