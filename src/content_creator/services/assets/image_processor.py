from pathlib import Path
from PIL import Image, ImageOps
from content_creator.schemas import ImageAsset
from content_creator.security.files import IMAGE_EXTENSIONS, validate_regular_file


def scan_and_process(input_dir: str | Path, project_dir: str | Path, max_size: tuple[int, int] = (1920, 1080)) -> list[ImageAsset]:
    source = Path(input_dir).resolve()
    if not source.is_dir():
        raise ValueError(f"image directory does not exist: {source}")
    root = Path(project_dir).resolve()
    original_dir = root / "materials" / "images"
    processed_dir = root / "materials" / "processed"
    original_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    assets: list[ImageAsset] = []
    for index, candidate in enumerate(sorted(source.iterdir())):
        if candidate.is_symlink() or candidate.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        path = validate_regular_file(candidate, IMAGE_EXTENSIONS)
        try:
            with Image.open(path) as opened:
                image = ImageOps.exif_transpose(opened).convert("RGB")
                image.load()
        except Exception as exc:
            raise ValueError(f"invalid image {path}: {exc}") from exc
        filename = f"{index:03d}_{path.stem}.jpg"
        image.thumbnail(max_size, Image.Resampling.LANCZOS)
        image.save(processed_dir / filename, "JPEG", quality=94, optimize=True)
        (original_dir / path.name).write_bytes(path.read_bytes())
        assets.append(ImageAsset(id=f"image-{index:03d}", filename=path.name, relative_path=f"materials/processed/{filename}", width=image.width, height=image.height, motion="static"))
    if not assets:
        raise ValueError("no valid images found")
    return assets
