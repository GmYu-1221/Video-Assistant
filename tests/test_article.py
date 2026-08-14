from pathlib import Path

import httpx
import pytest

from bs4 import BeautifulSoup

from content_creator.schemas import ArticleBrief, ArticleImage, AssetCandidate, AssetDecision, AssetKind, ImageRole, ImageTag, MusicTrack
from content_creator.services import article as article_service
from content_creator.services.article import BrowserImportRequired, _assert_public_url, _hamming_distance, _perceptual_hash, basic_asset_filter, discover_asset_candidates, download_selected_assets, order_images, parse_article_html, select_assets_with_agent
from content_creator.services.music.catalog import select_track


def _image(index: int) -> ArticleImage:
    return ArticleImage(id=f"article-{index:03d}", source_url="https://example.com/a.jpg", local_path=f"/tmp/{index}.jpg", width=1280, height=720, source_index=index, sha256=f"{index:064x}")


def test_private_urls_are_rejected():
    for url in ("http://127.0.0.1/article", "http://localhost/article", "file:///etc/passwd"):
        with pytest.raises(ValueError):
            _assert_public_url(url)


def test_tag_order_places_hero_first_and_result_last():
    images = [_image(index) for index in range(4)]
    tags = [ImageTag(image_id=images[0].id, role=ImageRole.evidence, salience=.7), ImageTag(image_id=images[1].id, role=ImageRole.hero, salience=.6), ImageTag(image_id=images[2].id, role=ImageRole.data, salience=.8), ImageTag(image_id=images[3].id, role=ImageRole.result, salience=.5)]
    ordered, contexts = order_images(images, tags)
    assert ordered[0].id == images[1].id
    assert ordered[-1].id == images[3].id
    assert contexts[-1].relation.value == "climax"


def test_music_selection_prefers_matching_mood_and_topic():
    tracks = [MusicTrack(id="default", path="input/bgm.wav", moods=["informative"]), MusicTrack(id="tech", path="input/tech.wav", moods=["tech"], topics=["ai"], energy=.7)]
    assert select_track(tracks, "tech", ["ai"]).id == "tech"


def test_perceptual_hash_identifies_identical_images(tmp_path):
    from PIL import Image
    first, second = tmp_path / "first.jpg", tmp_path / "second.jpg"
    Image.new("RGB", (1280, 720), "#224488").save(first)
    Image.new("RGB", (1280, 720), "#224488").save(second)
    assert _hamming_distance(_perceptual_hash(first), _perceptual_hash(second)) == 0


def test_asset_discovery_normalizes_srcset_picture_and_protocol_relative_urls(monkeypatch):
    brief = ArticleBrief(url="https://example.com/article", canonical_url="https://example.com/article", title="Example", text="article body")
    soup = BeautifulSoup("""<html><head><meta property='og:image' content='//cdn.example.com/social.png'></head><body>
    <picture><source srcset='//cdn.example.com/photo-small.jpg 320w, //cdn.example.com/photo-large.jpg 1600w'></picture>
    <img src='//cdn.example.com/photo-small.jpg' srcset='//cdn.example.com/photo-small.jpg 320w, //cdn.example.com/photo-large.jpg 1600w' alt='Article photo'>
    <img src='//cdn.example.com/diagram.svg' alt='Diagram'>
    </body></html>""", "html.parser")
    candidates, diagnostics = discover_asset_candidates(soup, brief)
    assert diagnostics["asset_discovery"]["srcset"] == 1
    assert diagnostics["asset_discovery"]["picture_source"] == 1
    assert diagnostics["asset_discovery"]["svg"] == 1
    assert all(item.source_url.startswith("https://") for item in candidates)
    assert any(item.source_url.endswith("photo-large.jpg") and "srcset" in item.source_types for item in candidates)


def test_asset_filter_and_agent_fallback_keep_non_ui_article_candidates(monkeypatch):
    brief = ArticleBrief(url="https://example.com/article", canonical_url="https://example.com/article", title="Example", text="article body")
    soup = BeautifulSoup("<img src='https://example.com/logo.svg'><img src='https://example.com/evidence.png' alt='Evidence'>", "html.parser")
    candidates, diagnostics = discover_asset_candidates(soup, brief)
    filtered = basic_asset_filter(candidates, diagnostics)
    assert [item.source_url for item in filtered] == ["https://example.com/evidence.png"]
    monkeypatch.setattr("content_creator.services.article.get_agent_provider", lambda _name: type("Provider", (), {"model_name": "mock"})())
    decisions = select_assets_with_agent(brief, filtered, diagnostics)
    assert decisions[0].selected is True
    assert diagnostics["asset_agent"]["mode"] == "local_fallback"


def test_browser_import_html_is_parsed_without_network_access():
    html = "<html><head><title>Imported</title></head><body><article><h1>Imported article</h1><p>" + ("正文内容 " * 30) + "</p><img src='https://cdn.example.com/hero.jpg' alt='hero'></article></body></html>"
    brief, soup = parse_article_html("https://example.com/article", html)
    assert brief.title == "Imported"
    assert len(brief.text) >= 80
    assert len(soup.select("article img")) == 1


def test_fetch_article_turns_401_403_into_browser_import_required(monkeypatch):
    request = httpx.Request("GET", "https://example.com/article")
    forbidden = httpx.HTTPStatusError("forbidden", request=request, response=httpx.Response(403, request=request))
    monkeypatch.setattr(article_service, "_get", lambda *_args, **_kwargs: (_ for _ in ()).throw(forbidden))
    with pytest.raises(BrowserImportRequired) as error:
        article_service.fetch_article("https://example.com/article")
    assert error.value.status_code == 403


def test_browser_asset_required_is_distinct_from_normal_download_failure(tmp_path, monkeypatch):
    candidate = AssetCandidate(id="asset-001", kind=AssetKind.image, source_url="https://cdn.example.com/protected.jpg", page_url="https://example.com/article")
    decision = AssetDecision(asset_id=candidate.id, selected=True, relevance=.9)
    request = httpx.Request("GET", candidate.source_url)
    forbidden = httpx.HTTPStatusError("forbidden", request=request, response=httpx.Response(403, request=request))

    def blocked(*_args, **_kwargs):
        raise forbidden

    monkeypatch.setattr(article_service, "_download_with_retry", blocked)
    diagnostics = {}
    assets = download_selected_assets([candidate], [decision], tmp_path, diagnostics, browser_imported=True)
    item = diagnostics["downloader"]["items"][0]
    assert assets == []
    assert item["status"] == "browser_asset_required"
    assert item["http_status"] == 403
    assert diagnostics["downloader"]["browser_asset_required"] == 1
    assert diagnostics["downloader"]["failed"] == 0
