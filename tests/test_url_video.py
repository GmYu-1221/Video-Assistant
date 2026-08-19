from pathlib import Path

import pytest
from PIL import Image

from content_creator.schemas import ArticleBrief, ArticleExtractionResult, ArticleImage, AssetCandidate, AssetDecision, AssetKind, BackgroundVideoConfig, ImageTag, VideoCopy
from content_creator.services import url_video


@pytest.fixture(autouse=True)
def deterministic_background_video(monkeypatch):
    monkeypatch.setattr(url_video, "_select_background_video", lambda *_args, **_kwargs: BackgroundVideoConfig(path="background/background.mp4", source_filename="test.mp4", duration=9, width=1080, height=1920))
    def still(_project, _remotion, output, _frame):
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1080, 1920), "black").save(path)
        return path
    monkeypatch.setattr(url_video, "render_layout_still", still)


def test_url_projects_force_reference_canvas(tmp_path, monkeypatch):
    stages = []
    sources = []
    for index in range(4):
        path = tmp_path / f"source-{index}.jpg"
        Image.new("RGB", (1280, 720), (index * 40, 20, 90)).save(path)
        sources.append(ArticleImage(id=f"article-{index:03d}", source_url="https://example.com/image.jpg", local_path=str(path), width=1280, height=720, source_index=index, sha256=f"{index:064x}"))
    brief = ArticleBrief(url="https://example.com/article", canonical_url="https://example.com/article", site_name="Example", title="示例文章", text="正文内容" * 100)
    extraction = ArticleExtractionResult(requested_url=brief.url, canonical_url=brief.canonical_url, effective_base_url=brief.url, extraction_method="test", extraction_confidence=1, title=brief.title, body=brief.text)
    monkeypatch.setattr(url_video, "fetch_article_with_extraction", lambda _: (extraction, object()))
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

    def download(*_args, **_kwargs):
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
    assert project.caption_template_plan is not None
    assert project.caption_template_plan.template_id == "reference_caption_v1"
    assert {binding.slot_id for binding in project.caption_template_plan.global_bindings} == {
        "title_primary", "title_secondary", "title_tertiary", "summary",
    }
    assert project.video_copy.headline
    assert stages == ["discovery", "filter", "agent", "download"]
    assert (Path(project.output.project_dir) / "asset_manifest.json").is_file()
    assert (Path(project.output.project_dir) / "caption_template_plan.json").is_file()


def test_browser_import_protected_asset_skips_second_agent_call(tmp_path, monkeypatch):
    sources = []
    candidates = []
    for index in range(4):
        path = tmp_path / f"imported-{index}.jpg"
        Image.new("RGB", (1280, 720), (index * 40, 20, 90)).save(path)
        url = f"https://cdn.example.com/image-{index}.jpg"
        sources.append(ArticleImage(id=f"article-{index:03d}", source_url=url, local_path=str(path), width=1280, height=720, source_index=index, sha256=f"{index:064x}"))
        candidates.append(AssetCandidate(id=f"asset-{index:03d}", kind=AssetKind.image, source_url=url, page_url="https://example.com/article", original_index=index))
    monkeypatch.setattr(url_video, "discover_asset_candidates", lambda *_: (candidates, {"asset_discovery": {}}))
    monkeypatch.setattr(url_video, "basic_asset_filter", lambda found, _diagnostics: found)
    monkeypatch.setattr(url_video, "select_assets_with_agent", lambda *_: [AssetDecision(asset_id=item.id, selected=True, role="diagram", relevance=.8) for item in candidates])

    def protected_download(_found, _decisions, _project_dir, diagnostics, **_kwargs):
        diagnostics["downloader"] = {"browser_asset_required": 1, "items": [{"asset_id": "asset-protected", "status": "browser_asset_required"}]}
        return sources

    monkeypatch.setattr(url_video, "download_selected_assets", protected_download)
    monkeypatch.setattr(url_video, "tag_images", lambda *_: pytest.fail("tag_images must not be called after protected browser assets"))
    monkeypatch.setattr(url_video, "compile_render_plan", lambda project, *_args, **_kwargs: project)
    html = "<article><h1>Imported article</h1><p>" + ("正文内容 " * 50) + "</p><p>" + ("更多正文 " * 50) + "</p></article>"
    project, _ = url_video.create_url_project("https://example.com/article", tmp_path / "output", imported_html=html)
    # The compact imported article needs one readable visual beat; additional
    # valid images no longer force an artificially long video.
    assert len(project.images) == 1
