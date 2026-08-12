from PIL import Image
from content_creator.services.assets import scan_and_process


def test_processing_preserves_aspect_ratio_without_crop(tmp_path):
    source = tmp_path / "images"
    source.mkdir()
    Image.new("RGB", (1080, 1920), "red").save(source / "portrait.png")
    assets = scan_and_process(source, tmp_path / "project", (1920, 1080))
    asset = assets[0]
    assert abs(asset.width / asset.height - 1080 / 1920) < 0.002
    assert asset.width <= 1920 and asset.height <= 1080
