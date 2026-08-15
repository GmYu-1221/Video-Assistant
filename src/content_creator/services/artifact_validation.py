"""Validation gate for a rendered URL-video artifact."""
from __future__ import annotations
import json
import subprocess
from pathlib import Path


def validate_final_artifact(path: str | Path, *, width: int = 1080, height: int = 1920, fps: float = 30.0, tolerance: float = .05) -> dict:
    target = Path(path)
    command = ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,avg_frame_rate,r_frame_rate", "-show_entries", "format=duration", "-of", "json", str(target)]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    result = {"path": str(target), "command": command, "returncode": completed.returncode, "passed": False, "errors": []}
    if completed.returncode:
        result["errors"].append(completed.stderr.strip() or "ffprobe failed")
        return result
    try:
        payload = json.loads(completed.stdout)
        videos = [stream for stream in payload.get("streams", []) if stream.get("codec_type") == "video"]
        if not videos:
            result["errors"].append("video stream is missing")
            return result
        stream = videos[0]
        rate = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "0/1"
        numerator, denominator = (float(value) for value in rate.split("/", 1))
        actual_fps = numerator / denominator if denominator else 0
        duration = float(payload.get("format", {}).get("duration") or 0)
        result.update({"video_stream_exists": True, "width": stream.get("width"), "height": stream.get("height"), "fps": actual_fps, "duration": duration, "raw": payload})
        if stream.get("width") != width: result["errors"].append(f"width must be {width}")
        if stream.get("height") != height: result["errors"].append(f"height must be {height}")
        if abs(actual_fps - fps) > tolerance: result["errors"].append(f"fps must be {fps}±{tolerance}")
        if duration <= 0: result["errors"].append("duration must be positive")
        result["passed"] = not result["errors"]
    except Exception as exc:
        result["errors"].append(f"invalid ffprobe output: {exc}")
    return result
