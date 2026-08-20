"""Prepare immutable browser runtime assets for one generated project."""
from __future__ import annotations

import shutil
from pathlib import Path


RUNTIME_ROOT = Path(__file__).resolve().parents[1] / "runtime"


def prepare_project_runtime(project_dir: str | Path) -> Path:
    project = Path(project_dir).resolve()
    target = project / "runtime"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(RUNTIME_ROOT, target)
    gsap = target / "gsap.min.js"
    if not gsap.is_file():
        raise RuntimeError("Vendored GSAP runtime is missing")
    return target
