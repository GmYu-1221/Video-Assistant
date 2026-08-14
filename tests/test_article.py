from io import BytesIO
from pathlib import Path

import httpx
import pytest

from bs4 import BeautifulSoup

from content_creator.schemas import ArticleBrief, ArticleImage, AssetCandidate, AssetDecision, AssetKind, ImageRole, ImageTag, MusicTrack
from content_creator.services import article as article_service
from content_creator.services.article import BrowserImportRequired, _assert_public_url, _clean_imported_article_document, _hamming_distance, _perceptual_hash, basic_asset_filter, discover_asset_candidates, download_selected_assets, order_images, parse_article_html, select_assets_with_agent
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
    from PIL import Image, ImageDraw
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


def test_imported_html_rejects_invalid_canonical_and_preserves_requested_identity():
    html = "<html><head><meta property='og:url' content='https://www.zhihu.com/question/undefined/answer/42'><title>Imported</title></head><body><article><p>" + ("正文内容 " * 30) + "</p></article></body></html>"
    brief, _ = parse_article_html("https://www.zhihu.com/question/1/answer/42", html)
    assert brief.requested_url == "https://www.zhihu.com/question/1/answer/42"
    assert brief.canonical_url == brief.requested_url
    assert brief.effective_base_url == brief.requested_url


def test_discovery_keeps_data_original_and_marks_article_content():
    brief = ArticleBrief(url="https://example.com/a", canonical_url="https://example.com/a", effective_base_url="https://example.com/a", title="Example", text="body")
    soup = BeautifulSoup("<article><figure><img src='avatar.jpg' srcset='avatar.jpg 320w' data-original='full.jpg' alt='Chart'><figcaption>Results</figcaption></figure></article>", "html.parser")
    candidates, _ = discover_asset_candidates(soup, brief)
    by_url = {item.source_url: item for item in candidates}
    assert "https://example.com/full.jpg" in by_url
    assert "data-original" in by_url["https://example.com/full.jpg"].source_types
    assert "article-content" in by_url["https://example.com/full.jpg"].source_types


def test_agent_empty_response_retries_without_truncating_candidate_pool(monkeypatch):
    brief = ArticleBrief(url="https://example.com/a", canonical_url="https://example.com/a", title="Example", text="body")
    candidates = [AssetCandidate(id=f"asset-{index:03d}", kind=AssetKind.image, source_url=f"https://example.com/{index}.jpg", page_url=brief.url, original_index=index) for index in range(4)]
    payload = {"asset_decisions": [{"asset_id": candidate.id, "selected": index < 2, "relevance": .9 - index / 10} for index, candidate in enumerate(candidates)]}

    class Provider:
        model_name = "gemini-3.6-flash"
        def complete_json(self, _prompt): return ""
        def complete(self, _prompt): return __import__("json").dumps(payload)

    monkeypatch.setattr(article_service, "get_agent_provider", lambda _name: Provider())
    diagnostics = {}
    decisions = select_assets_with_agent(brief, candidates, diagnostics)
    assert {decision.asset_id for decision in decisions} == {candidate.id for candidate in candidates}
    assert diagnostics["asset_agent"]["mode"] == "text_retry_success"


def test_downloader_backfills_from_unselected_candidate_pool(tmp_path, monkeypatch):
    from PIL import Image, ImageDraw

    candidates = [AssetCandidate(id=f"asset-{index:03d}", kind=AssetKind.image, source_url=f"https://cdn.example.com/{index}.jpg", page_url="https://example.com/a", original_index=index, source_types=["data-original", "article-content"] if index else ["srcset"]) for index in range(5)]
    decisions = [AssetDecision(asset_id=candidate.id, selected=candidate.id == "asset-000", relevance=.9 if candidate.id == "asset-000" else .5) for candidate in candidates]
    small = BytesIO()
    Image.new("RGB", (40, 40), "#225588").save(small, "JPEG")

    def download(_client, url, _limit):
        if url.endswith("/0.jpg"):
            content = small.getvalue()
        else:
            full = BytesIO()
            index = int(url.rsplit("/", 1)[-1].split(".", 1)[0])
            image = Image.new("RGB", (640, 480), (index * 40, 70, 150))
            ImageDraw.Draw(image).rectangle((index * 80, 0, index * 80 + 120, 480), fill="#ffffff")
            image.save(full, "JPEG")
            content = full.getvalue()
        return httpx.Response(200, content=content, headers={"content-type": "image/jpeg"}, request=httpx.Request("GET", url))

    monkeypatch.setattr(article_service, "_download_with_retry", download)
    diagnostics = {}
    assets = download_selected_assets(candidates, decisions, tmp_path, diagnostics, max_renderable=4)
    assert len(assets) == 4
    assert diagnostics["downloader"]["attempted"] == 5
    assert diagnostics["downloader"]["candidate_pool_exhausted"] is False


def test_imported_screenshot_document_is_inert_article_fragment():
    document = _clean_imported_article_document("<html><body><script>window.pwned=true</script><article onclick='bad()'><p>正文</p><img src='https://cdn.example.com/a.jpg' onerror='bad()'><iframe src='https://example.com'></iframe></article></body></html>", "https://example.com/a")
    assert "window.pwned" not in document
    assert "onclick" not in document
    assert "onerror" not in document
    assert "iframe" not in document
    assert "https://cdn.example.com/a.jpg" not in document
    assert "正文" in document


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
