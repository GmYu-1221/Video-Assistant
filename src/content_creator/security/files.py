from pathlib import Path

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac"}


def safe_child(root: str | Path, relative: str | Path) -> Path:
    root_path = Path(root).resolve()
    candidate = (root_path / relative).resolve()
    try:
        candidate.relative_to(root_path)
    except ValueError as exc:
        raise ValueError("path escapes project root") from exc
    if Path(relative).is_absolute():
        raise ValueError("absolute paths are not allowed")
    return candidate


def validate_regular_file(path: str | Path, allowed: set[str]) -> Path:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError(f"not a regular file: {candidate}")
    if candidate.suffix.lower() not in allowed:
        raise ValueError(f"unsupported extension: {candidate.suffix}")
    return candidate.resolve()
