"""Render the standalone reference_caption_v1 feasibility proof."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote

from content_creator.services.server import MediaServer
from content_creator.services.title_normalization import article_title_candidates


AUDIT_PATTERN = re.compile(r"\[REFERENCE_CAPTION_AUDIT\](\{.*?\})(?:\r?\n|$)", re.DOTALL)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _media_url(base_url: str, repo_root: Path, path: Path) -> str:
    relative = path.resolve().relative_to(repo_root.resolve()).as_posix()
    return f"{base_url.rstrip('/')}/{quote(relative, safe='/')}"


def build_poc_props(project_dir: str | Path, background_path: str | Path, base_url: str, repo_root: str | Path, *, media_path_override: str | Path | None = None) -> dict:
    project = Path(project_dir).resolve()
    root = Path(repo_root).resolve()
    render_data = json.loads((project / "render_data.json").read_text(encoding="utf-8"))
    viral_path = project / "viral_copy_plan.json"
    viral = json.loads(viral_path.read_text(encoding="utf-8")) if viral_path.is_file() else {"content_units": []}

    raw_title = render_data["persistent_title"]["content"]
    normalized_title = (article_title_candidates(raw_title) or [raw_title])[0]
    title_parts = [part.strip() for part in re.split(r"[：:]", normalized_title, maxsplit=1) if part.strip()]
    first_line = title_parts[0]
    second_line = title_parts[1] if len(title_parts) > 1 else normalized_title
    second_line = re.split(r"\s+-\s+", second_line, maxsplit=1)[0].strip()
    first_image = render_data["images"][0]
    third_line = render_data["timeline"][0]["narrative"]["contents"][0]["short"]

    summary_parts: list[str] = []
    summary_length = 0
    units = viral.get("content_units", [])
    ordered_units = sorted(
        units,
        key=lambda unit: {"opening": 0, "explanation": 1, "evidence": 2, "conclusion": 3}.get(unit.get("purpose"), 2),
    )
    for unit in ordered_units:
        value = re.sub(r"\s+", " ", str(unit.get("full", ""))).strip()
        if not value or value.endswith(("？", "?")) or value in summary_parts:
            continue
        summary_parts.append(value)
        summary_length += len(value)
        if summary_length >= 150 or len(summary_parts) >= 4:
            break
    if not summary_parts:
        summary_parts = [item["full"] for item in render_data["timeline"][0]["narrative"]["contents"]]

    media_path = Path(media_path_override) if media_path_override else project / first_image["relative_path"]
    return {
        "topLines": [first_line, second_line, third_line],
        "summary": "".join(summary_parts),
        "mediaUrl": _media_url(base_url, root, media_path),
        "backgroundVideoUrl": _media_url(base_url, root, Path(background_path)),
        "headlineFontId": "zcool-qingke-huangyou",
        "bodyFontId": "noto-sans-sc",
    }


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=cwd, check=False, capture_output=True, text=True)
    if completed.returncode:
        tail = ((completed.stdout or "") + "\n" + (completed.stderr or ""))[-2000:]
        raise RuntimeError(f"Command failed ({completed.returncode}): {' '.join(command)}\n{tail}")
    return completed


def _audit_from(completed: subprocess.CompletedProcess[str]) -> dict:
    combined = (completed.stdout or "") + "\n" + (completed.stderr or "")
    matches = AUDIT_PATTERN.findall(combined)
    if not matches:
        raise RuntimeError(
            "Reference caption render did not emit a DOM audit. "
            f"Remotion output tail:\n{combined[-4000:]}"
        )
    return json.loads(matches[-1])


def validate_layout_audit(audit: dict, expected_frame: int) -> None:
    if audit.get("templateId") != "reference_caption_v1" or audit.get("frame") != expected_frame:
        raise ValueError("Reference caption audit identity mismatch")
    if audit.get("error"):
        raise ValueError(f"Reference caption DOM audit failed: {audit['error']}")
    if not audit.get("fontsReady"):
        families = {item.get("id"): item.get("fontFamily") for item in audit.get("blocks", [])}
        raise ValueError(f"Reference caption fonts did not load: {families}")
    if (
        audit.get("mediaObjectFit") != "contain"
        or audit.get("mediaObjectPosition") not in {"50% 50%", "center"}
        or int(audit.get("backgroundZIndex", -1)) != 0
    ):
        raise ValueError("Reference caption media/background contract failed")
    blocks = {item["id"]: item for item in audit.get("blocks", [])}
    expected = {
        "top-primary": (60, 92, 960, 96),
        "top-secondary": (60, 210, 960, 108),
        "top-tertiary": (60, 352, 960, 84),
        "media": (0, 655, 1080, 610),
        "summary": (80, 1325, 920, 500),
    }
    for block_id, geometry in expected.items():
        block = blocks.get(block_id)
        if block is None:
            raise ValueError(f"Reference caption audit missing block: {block_id}")
        actual = tuple(round(float(block[key])) for key in ("x", "y", "width", "height"))
        if actual != geometry:
            raise ValueError(f"Reference caption geometry mismatch for {block_id}: {actual}")
        if block["scrollWidth"] > block["clientWidth"] + 1 or block["scrollHeight"] > block["clientHeight"] + 1:
            raise ValueError(f"Reference caption overflow: {block_id}")
        x, y, width, height = actual
        if x < 0 or y < 0 or x + width > 1080 or y + height > 1920:
            raise ValueError(f"Reference caption canvas overflow: {block_id}")
        if int(block.get("effectiveZIndex", block.get("zIndex", 0))) <= int(audit["backgroundZIndex"]):
            raise ValueError(f"Reference caption layer is not above background: {block_id}")
    ordered = list(expected)
    for index, left_id in enumerate(ordered):
        left = expected[left_id]
        for right_id in ordered[index + 1:]:
            right = expected[right_id]
            intersects = left[0] < right[0] + right[2] and left[0] + left[2] > right[0] and left[1] < right[1] + right[3] and left[1] + left[3] > right[1]
            if intersects:
                raise ValueError(f"Reference caption collision: {left_id}/{right_id}")


def _ffprobe(path: Path) -> dict:
    completed = _run([
        "ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,r_frame_rate",
        "-show_entries", "format=duration", "-of", "json", str(path),
    ], cwd=path.parent)
    data = json.loads(completed.stdout)
    video = next((stream for stream in data.get("streams", []) if stream.get("codec_type") == "video"), None)
    if not video or video.get("width") != 1080 or video.get("height") != 1920:
        raise ValueError("Reference caption MP4 has invalid video geometry")
    numerator, denominator = (int(value) for value in video["r_frame_rate"].split("/"))
    fps = numerator / denominator
    duration = float(data["format"]["duration"])
    if abs(fps - 30) > .05 or duration <= 0:
        raise ValueError("Reference caption MP4 has invalid fps or duration")
    return data | {"validation": {"passed": True, "fps": fps, "duration": duration}}


def render_reference_caption_poc(project_dir: str | Path, output_dir: str | Path, background_path: str | Path) -> Path:
    root = _repo_root()
    remotion_dir = root / "remotion"
    project = Path(project_dir).resolve()
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    render_data = json.loads((project / "render_data.json").read_text(encoding="utf-8"))
    source_media = project / render_data["images"][0]["relative_path"]
    copied_media = output / "materials/hero.jpg"
    copied_background = output / "background/background.mp4"
    copied_media.parent.mkdir(parents=True, exist_ok=True)
    copied_background.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_media, copied_media)
    shutil.copy2(Path(background_path), copied_background)
    server = MediaServer(output)
    base_url = server.start()
    try:
        props = build_poc_props(project, copied_background, base_url, output, media_path_override=copied_media)
        props_path = output / "props.json"
        props_path.write_text(json.dumps(props, ensure_ascii=False, indent=2), encoding="utf-8")
        completed = _run([
            "node", "scripts/render-reference-caption-audit.mjs", str(props_path),
            str(output / "first-frame.png"), str(output / "preview.png"),
        ], cwd=remotion_dir)
        parsed_audits = [json.loads(value) for value in AUDIT_PATTERN.findall(
            (completed.stdout or "") + "\n" + (completed.stderr or "")
        )]
        audits_by_frame = {int(audit["frame"]): audit for audit in parsed_audits}
        if 0 not in audits_by_frame or 30 not in audits_by_frame:
            _audit_from(completed)
            raise RuntimeError(
                "Expected reference caption audits for frames 0 and 30, "
                f"received {sorted(audits_by_frame)}"
            )
        audits = {"first_frame": audits_by_frame[0], "settled": audits_by_frame[30]}
        validate_layout_audit(audits["first_frame"], 0)
        validate_layout_audit(audits["settled"], 30)
        if audits["first_frame"]["topGroupOpacity"] != 0 or audits["settled"]["topGroupOpacity"] < .999:
            raise ValueError("Reference caption title must fade once and remain settled")
        if [item["textContent"] for item in audits["first_frame"]["blocks"][:3]] != [item["textContent"] for item in audits["settled"]["blocks"][:3]]:
            raise ValueError("Reference caption top copy changed between frames")
        (output / "layout-audit.json").write_text(json.dumps(audits, ensure_ascii=False, indent=2), encoding="utf-8")

        target = output / "sample.mp4"
        _run([
            "pnpm", "exec", "remotion", "render", "src/index.ts", "ReferenceCaptionV1",
            str(target), "--props", str(props_path), "--log", "verbose",
        ], cwd=remotion_dir)
        probe = _ffprobe(target)
        (output / "ffprobe.json").write_text(json.dumps(probe, ensure_ascii=False, indent=2), encoding="utf-8")
        return target
    finally:
        server.close()


def main() -> None:
    root = _repo_root()
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", default=str(root / "output/projects/20260818_180529_712252"))
    parser.add_argument("--background", default=str(root / "input/bgv/1-space-flythrough.mp4"))
    parser.add_argument("--output-dir", default=str(root / "output/templates/reference-caption-v1"))
    args = parser.parse_args()
    target = render_reference_caption_poc(args.project_dir, args.output_dir, args.background)
    print(target)


if __name__ == "__main__":
    main()
