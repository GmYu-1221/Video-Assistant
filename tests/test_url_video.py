from pathlib import Path

from PIL import Image

from content_creator.schemas import ArticleBrief, ArticleImage, AssetCandidate, AssetDecision, AssetKind, ImageTag, VideoCopy
from content_creator.services import url_video


def test_url_projects_force_reference_canvas(tmp_path, monkeypatch):
    stages = []
    sources = []
    for index in range(4):
        path = tmp_path / f"source-{index}.jpg"
        Image.new("RGB", (1280, 720), (index * 40, 20, 90)).save(path)
        sources.append(ArticleImage(id=f"article-{index:03d}", source_url="https://example.com/image.jpg", local_path=str(path), width=1280, height=720, source_index=index, sha256=f"{index:064x}"))
    brief = ArticleBrief(url="https://example.com/article", canonical_url="https://example.com/article", site_name="Example", title="示例文章", text="正文内容" * 100)
    monkeypatch.setattr(url_video, "fetch_article", lambda _: (brief, object()))
    candidates = [AssetCandidate(id=f"asset-{index:03d}", kind=AssetKind.image, source_url=f"https://example.com/image-{index}.jpg", page_url=brief.canonical_url, original_index=index) for index in range(4)]
    def discover(*_args):
        stages.append("discovery")
        return candidates, {"asset_discovery": {}}

    def filter_assets(found, _diagnostics):
        stages.append("filter")
        return found

    def select(*_args):
        stages.append("agent")
        return [AssetDecision(asset_id=item.id, selected=True, relevance=.8) for item in candidates]

    def download(*_args):
        stages.append("download")
        return sources

    monkeypatch.setattr(url_video, "discover_asset_candidates", discover)
    monkeypatch.setattr(url_video, "basic_asset_filter", filter_assets)
    monkeypatch.setattr(url_video, "select_assets_with_agent", select)
    monkeypatch.setattr(url_video, "download_selected_assets", download)
    monkeypatch.setattr(url_video, "tag_images", lambda current, images: (current, VideoCopy(headline="标题", subtitle="副标题", body="正文"), [ImageTag(image_id=image.id, salience=.6, section_index=index) for index, image in enumerate(images)]))
    monkeypatch.setattr(url_video, "compile_render_plan", lambda project, *_args, **_kwargs: project)
    project, _ = url_video.create_url_project("https://example.com/article", tmp_path / "output")
    assert (project.width, project.height, project.fps) == (1080, 1920, 30)
    assert project.video_copy.headline == "标题"
    assert stages == ["discovery", "filter", "agent", "download"]
    assert (Path(project.output.project_dir) / "asset_manifest.json").is_file()
