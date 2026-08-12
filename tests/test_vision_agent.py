from PIL import Image
from content_creator.schemas import ImageAsset, RGBColor
from content_creator.agents.vision_agent import analyze_asset

def test_vision_analysis_is_valid(tmp_path):
    (tmp_path / "materials/processed").mkdir(parents=True)
    Image.new("RGB", (100, 50), "red").save(tmp_path / "materials/processed/a.jpg")
    asset = ImageAsset(id="a", filename="a.jpg", relative_path="materials/processed/a.jpg", width=100, height=50, backgroundColor=RGBColor(r=255,g=0,b=0))
    result = analyze_asset(asset, str(tmp_path))
    assert result.image_id == "a" and result.aspect_ratio == 2
    assert 0 <= result.information_density <= 1
