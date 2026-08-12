from PIL import Image, ImageFilter, ImageStat
from content_creator.schemas import ImageAnalysis, ImageAsset

def analyze_asset(asset: ImageAsset, project_dir: str | None = None) -> ImageAnalysis:
    density = 0.5
    if project_dir:
        path = __import__('pathlib').Path(project_dir) / asset.relative_path
        try:
            with Image.open(path).convert('RGB') as image:
                small = image.resize((min(128, image.width), min(128, image.height))).filter(ImageFilter.FIND_EDGES)
                edge = ImageStat.Stat(small).mean
                density = max(0.0, min(1.0, sum(edge) / (len(edge) * 255)))
        except (OSError, ValueError):
            density = 0.5
    color = asset.backgroundColor.model_dump()
    return ImageAnalysis(image_id=asset.id, width=asset.width, height=asset.height, aspect_ratio=asset.width / asset.height, dominant_color=color, information_density=round(density, 4), recommended_duration=60)

def vision_node(state: dict) -> dict:
    project = state["project"]
    analyses = [analyze_asset(asset, project.output.project_dir) for asset in project.images]
    return {"image_analysis": analyses}
