from io import BytesIO
import json
from pathlib import Path

import httpx
import pytest

from bs4 import BeautifulSoup

from content_creator.schemas import ArticleBrief, ArticleImage, AssetCandidate, AssetDecision, AssetKind, ImageRole, ImageTag, MusicTrack
from content_creator.services import article as article_service
from content_creator.services.article import BrowserImportRequired, _assert_public_url, _build_screenshot_document, _clean_imported_article_document, _deduplicate_text_candidates, _discover_text_candidates, _hamming_distance, _is_verified_title_card, _merge_text_candidates, _perceptual_hash, _quality_ok, _select_article_candidates, _screenshot_anchors, analyze_prominent_headlines, basic_asset_filter, capture_article_screenshots, chromium_available, classify_content_sufficiency, discover_asset_candidates, download_selected_assets, extract_article_html, order_images, parse_article_html, select_assets_with_agent
from content_creator.services.music.catalog import select_track


def _image(index: int) -> ArticleImage:
    return ArticleImage(id=f"article-{index:03d}", source_url="https://example.com/a.jpg", local_path=f"/tmp/{index}.jpg", width=1280, height=720, source_index=index, sha256=f"{index:064x}")


def test_private_urls_are_rejected():
    for url in ("http://127.0.0.1/article", "http://localhost/article", "file:///etc/passwd"):
        with pytest.raises(ValueError):
            _assert_public_url(url)


def test_plain_text_angle_bracket_placeholders_are_not_parsed_as_html():
    body = "安装命令使用 <skill-name> 参数。\n" + ("这是完整的中文说明段落，介绍参数用途和执行结果。" * 8)
    classification, metrics = classify_content_sufficiency(body, representation="text")
    assert classification in {"compact", "normal"}
    assert metrics["paragraph_count"] == 2
    assert _quality_ok(body)


def test_single_substantive_paragraph_can_form_compact_video():
    body = "这一段正文完整说明工具的用途、安装方式、执行步骤、适用范围和最终效果，内容虽然简短但具有独立且可追溯的事实。" * 3
    classification, metrics = classify_content_sufficiency(body)
    assert classification == "compact"
    assert metrics["paragraph_count"] == 1


def test_short_navigation_text_remains_invalid_article_content():
    body = "首页\n登录\n注册\n收藏\n分享\n上一页\n下一页"
    classification, _ = classify_content_sufficiency(body)
    assert classification == "invalid"


def test_tag_order_places_hero_first_and_result_last():
    images = [_image(index) for index in range(4)]
    tags = [ImageTag(image_id=images[0].id, role=ImageRole.evidence, salience=.7), ImageTag(image_id=images[1].id, role=ImageRole.hero, salience=.6), ImageTag(image_id=images[2].id, role=ImageRole.data, salience=.8), ImageTag(image_id=images[3].id, role=ImageRole.result, salience=.5)]
    ordered, contexts = order_images(images, tags)
    assert ordered[0].id == images[1].id
    assert ordered[-1].id == images[3].id
    assert contexts[-1].relation.value == "climax"


def test_verified_title_card_is_selected_first_even_with_lower_salience():
    images = [_image(index) for index in range(3)]
    tags = [
        ImageTag(image_id=images[0].id, role=ImageRole.hero, salience=.95),
        ImageTag(image_id=images[1].id, role=ImageRole.overview, salience=.55, contains_prominent_headline=True, embedded_headline_text="Qwen3.8-Max 登场", headline_prominence=.9, headline_title_match_score=.92, headline_bbox=(.05, .15, .9, .35), headline_readability=.94, headline_analysis_status="verified"),
        ImageTag(image_id=images[2].id, role=ImageRole.result, salience=.5),
    ]
    ordered, _ = order_images(images, tags, title="Qwen3.8-Max 正式发布", target_count=3)
    assert ordered[0].id == images[1].id
    assert _is_verified_title_card(images[1], tags[1])


def test_verified_article_screenshot_can_be_prominent_headline_opener():
    images = [_image(0), _image(1).model_copy(update={"source_url": "screenshot://article/1"})]
    tags = [
        ImageTag(image_id=images[0].id, role=ImageRole.hero, salience=.6),
        ImageTag(image_id=images[1].id, role=ImageRole.overview, salience=.99, contains_prominent_headline=True, embedded_headline_text="正文截图大字", headline_prominence=1, headline_title_match_score=1, headline_bbox=(0, 0, 1, .5), headline_readability=1, headline_analysis_status="verified"),
    ]
    ordered, _ = order_images(images, tags, title="正文截图大字")
    assert ordered[0].id == images[1].id
    assert _is_verified_title_card(images[1], tags[1])


def test_unverified_headline_metadata_does_not_claim_title_card():
    image = _image(0)
    tag = ImageTag(image_id=image.id, role=ImageRole.hero, contains_prominent_headline=True, embedded_headline_text="Metadata guess", headline_prominence=1, headline_title_match_score=1, headline_readability=1, headline_analysis_status="unavailable")
    assert not _is_verified_title_card(image, tag)


def test_prominent_headline_analysis_batches_actual_images(monkeypatch):
    images = [_image(index) for index in range(9)]
    images[0] = images[0].model_copy(update={"source_url": "screenshot://article/0"})
    tags = [ImageTag(image_id=image.id, role=ImageRole.demo if index == 0 else ImageRole.evidence) for index, image in enumerate(images)]
    calls = []

    class Provider:
        model_name = "gemini-3.6-flash"

        def complete_multimodal(self, prompt, paths):
            payload = json.loads(prompt)
            ids = [item["image_id"] for item in payload["images_in_supplied_order"]]
            calls.append((ids, paths))
            return json.dumps({"image_headlines": [{"image_id": image_id, "contains_prominent_headline": image_id == images[0].id, "embedded_headline_text": "DeepSeek-V3" if image_id == images[0].id else "", "headline_prominence": .9 if image_id == images[0].id else 0, "headline_title_match_score": .95 if image_id == images[0].id else 0, "headline_bbox": [.1, .1, .8, .3] if image_id == images[0].id else [0, 0, 0, 0], "headline_readability": .9 if image_id == images[0].id else 0, "headline_exclusion_reason": "" if image_id == images[0].id else "no prominent headline"} for image_id in ids]})

    monkeypatch.setattr(article_service, "get_agent_provider", lambda _name: Provider())
    brief = ArticleBrief(url="https://example.com", canonical_url="https://example.com", title="DeepSeek-V3 项目介绍", text="正文")
    analyzed = analyze_prominent_headlines(brief, images, tags)
    assert [len(ids) for ids, _ in calls] == [4, 4, 1]
    assert analyzed[0].headline_analysis_status == "verified"
    assert _is_verified_title_card(images[0], analyzed[0])
    assert all(tag.headline_analysis_status == "verified" for tag in analyzed)


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
    html = "<html><head><title>Imported</title></head><body><article><h1>Imported article</h1><p>" + ("正文内容 " * 15) + "</p><p>" + ("更多正文 " * 15) + "</p><img src='https://cdn.example.com/hero.jpg' alt='hero'></article></body></html>"
    brief, soup = parse_article_html("https://example.com/article", html)
    assert brief.title == "Imported"
    assert len(brief.text) >= 80
    assert len(soup.select("article img")) == 1


def test_imported_html_rejects_invalid_canonical_and_preserves_requested_identity():
    html = "<html><head><meta property='og:url' content='https://www.zhihu.com/question/undefined/answer/42'><title>Imported</title></head><body><article><p>" + ("正文内容 " * 15) + "</p><p>" + ("更多正文 " * 15) + "</p></article></body></html>"
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


def test_screenshot_document_uses_selected_html_and_removes_network_capable_markup():
    html = "<main><script>window.pwned=true</script><h2 onclick='bad()'>小节</h2><p>第一段正文</p><img src='https://cdn.example.com/a.jpg'><a href='https://example.com'>链接</a><form action='https://example.com'><input></form></main>"
    document, source, stats = _build_screenshot_document(html, "备用正文", "文章标题")
    assert source == "selected_html"
    assert stats["cleaned_chars"] >= len("第一段正文")
    assert "window.pwned" not in document
    assert "onclick" not in document
    assert "cdn.example.com" not in document
    assert "https://example.com" not in document
    assert "#video-assistant-article" in document
    assert "Video Assistant Noto" in document


def test_github_page_chrome_is_removed_but_readme_body_is_kept():
    html = """<main>
      <div class='repo-nav'><span>Notifications</span><span>Fork 16.7k</span><span>Star 104k</span></div>
      <div class='file-list'><h2>Folders and files</h2><span>Last commit</span><span>History</span></div>
      <div class='markdown-body'><h1>DeepSeek-V3</h1>
        <p>DeepSeek-V3 is a strong mixture-of-experts language model with efficient training.</p>
        <p>The model uses multi-head latent attention and a multi-token prediction objective.</p>
      </div>
    </main>"""
    candidates = _deduplicate_text_candidates(_discover_text_candidates(html, BeautifulSoup(html, "html.parser"), "DeepSeek-V3"))
    assert candidates
    selected = max(candidates, key=lambda item: item.char_count)
    assert "Notifications" not in selected.text
    assert "Folders and files" not in selected.text
    assert "DeepSeek-V3 is a strong" in selected.text


def test_screenshot_document_reports_ui_cleanup_and_keeps_readme_text():
    html = """<main><div class='repo-nav'><span>Notifications</span><span>Fork 16.7k</span></div>
      <div class='markdown-body'><h2>Introduction</h2><p>这是 README 正文，包含足够的技术说明和背景信息。</p>
      <p>第二段正文用于截图兜底，不是页面导航。</p></div></main>"""
    document, source, stats = _build_screenshot_document(html, "", "DeepSeek-V3")
    assert source == "selected_html"
    assert stats["ui_nodes_removed"] >= 1
    assert stats["ui_token_hits"]
    assert "Notifications" not in document
    assert "Fork 16.7k" not in document
    assert "这是 README 正文" in document


def test_screenshot_document_uses_extracted_body_when_html_is_empty():
    document, source, stats = _build_screenshot_document("", "第一段正文。\n\n第二段正文。", "文章标题")
    assert source == "extracted_body"
    assert stats["paragraph_count"] == 2
    assert "第一段正文" in document
    assert "第二段正文" in document


def test_screenshot_anchors_are_clamped_and_prioritize_distinct_paragraphs():
    class Locator:
        def count(self): return 5
        def nth(self, index):
            return type("Paragraph", (), {"bounding_box": lambda self: {"x": 80, "y": index * 500, "width": 1000, "height": 80}})()

    class Main:
        def locator(self, _selector): return Locator()

    anchors = _screenshot_anchors(Main(), {"x": 80, "y": 0, "width": 1120, "height": 2400}, 630, 1800, 4)
    assert len(anchors) >= 4
    assert all(0 <= top <= 1800 for top, _ in anchors)
    assert len({round(top) for top, _ in anchors[:4]}) == 4


@pytest.mark.skipif(not chromium_available(), reason="Playwright Chromium is not installed")
def test_local_screenshot_fallback_never_navigates_to_source_url(tmp_path):
    paragraphs = "".join(f"<p>第 {index} 段正文，包含足够长的内容用于不同截图画面。" + ("更多说明文字。" * 16) + "</p>" for index in range(16))
    diagnostics = {}
    assets = capture_article_screenshots(
        "https://blocked.example.com/article",
        tmp_path,
        0,
        2,
        diagnostics,
        selected_html=f"<article>{paragraphs}</article>",
        title="本地正文截图",
    )
    fallback = diagnostics["screenshot_fallback"]
    assert len(assets) == 2
    assert fallback["network_navigation"] is False
    assert fallback["source"] == "selected_html"
    assert all(Path(asset.local_path).is_file() for asset in assets)
    assert all(asset.source_url.startswith("screenshot://article/") for asset in assets)
    assert all(clip["x"] >= 0 and clip["y"] >= 0 and clip["right"] <= fallback["page_size"]["scrollWidth"] and clip["bottom"] <= fallback["page_size"]["scrollHeight"] for clip in fallback["clips"])


def test_cctv_script_html_candidate_restores_body_and_images(monkeypatch):
    html = """<html><head><title>抗台风</title></head><body><div id='text_area'></div>
    <script>var contentdate = '<p><img src=\"https://cdn.example.com/one.jpg\">第一段正文内容，描述新闻背景、现场情况和文章主题。</p><p>第二段正文介绍阻尼器的工作原理以及工程技术细节和安全价值。</p><p><img src=\"https://cdn.example.com/two.jpg\">第三段正文内容，说明后续技术方案、实际效果和发展方向。</p>';</script>
    </body></html>"""
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    extraction, _ = extract_article_html("https://example.com/a", html)
    assert extraction.extraction_method == "script_html"
    assert len(extraction.body) >= 50
    assert extraction.selected_html.count("<img") == 2
    assert extraction.selected_candidate_ids


def test_jsonld_body_candidate_is_discovered():
    payload = json.dumps({"@type": "NewsArticle", "articleBody": "第一段新闻正文。\n第二段新闻正文。" + ("新闻内容 " * 20)}, ensure_ascii=False)
    soup = BeautifulSoup(f"<html><head><script type='application/ld+json'>{payload}</script></head><body></body></html>", "html.parser")
    candidates = _discover_text_candidates(str(soup), soup, "新闻标题")
    assert any(item.source == "jsonld" and item.paragraph_count == 1 for item in candidates)


def test_candidate_deduplication_prevents_duplicate_merge():
    html = "<article><p>" + ("相同的第一段正文。" * 8) + "</p><p>" + ("相同的第二段正文。" * 8) + "</p></article>"
    soup = BeautifulSoup(html, "html.parser")
    first = _discover_text_candidates(html, soup, "标题")
    second = [item.model_copy(update={"id": "duplicate-copy", "source": "script_html"}) for item in first]
    candidates = _deduplicate_text_candidates(first + second)
    merged = _merge_text_candidates(candidates, [item.id for item in candidates])
    assert len(merged.body.splitlines()) == 2


def test_article_agent_receives_previews_only(monkeypatch):
    brief = ArticleBrief(url="https://example.com/a", canonical_url="https://example.com/a", title="Example", text="body")
    soup = BeautifulSoup("<article><p>" + ("开头标记 " * 100) + "中间标记" + (" 结尾标记" * 100) + "</p><p>第二段。</p></article>", "html.parser")
    candidates = _deduplicate_text_candidates(_discover_text_candidates(str(soup), soup, brief.title))
    seen = {}

    class Provider:
        model_name = "article-test"
        def complete_json(self, prompt):
            seen["prompt"] = prompt
            return '{"selected_candidate_ids":["text-000"],"confidence":0.9,"reason":"正文"}'
        def complete(self, prompt):
            return self.complete_json(prompt)

    monkeypatch.setattr(article_service, "get_agent_provider", lambda _name: Provider())
    extraction, _diagnostics = _select_article_candidates(candidates, brief.title)
    assert len(extraction.body) > 500
    assert "开头标记" in seen["prompt"]
    assert extraction.body not in seen["prompt"]


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


def test_blog_post_body_beats_short_metadata_and_drives_asset_target(monkeypatch):
    topics = [
        "平台先统一管理采集的工业图像，并按照项目与任务组织数据集。",
        "标注工具支持实例分割，操作者可以检查轮廓并修正对象边界。",
        "模型训练记录参数、版本和指标，便于团队比较不同实验结果。",
        "自动标注读取已有样本并生成候选区域，人工确认后进入训练集。",
        "模型测试展示检测框、置信度与错误样本，帮助定位实际问题。",
        "部署完成后进入实时视觉分析，并把异常结果发送到告警中心。",
    ]
    paragraphs = "".join(
        f"<p>第{index}部分。" + topic * 7 + f"<img src='https://img.example.com/{index}.png' alt='步骤{index}'></p>"
        for index, topic in enumerate(topics)
    )
    html = f"""<html><head><title>视觉分析平台升级</title>
    <meta name='description' content='只有一行的页面摘要，不能替代完整正文。'></head>
    <body><div class='postBody'><div id='cnblogs_post_body' class='blogpost-body'>{paragraphs}</div></div></body></html>"""
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    extraction, _ = extract_article_html("https://example.com/post", html, allow_rendered_fallback=False)
    assert extraction.extraction_method == "dom"
    assert len(extraction.body) > 1200
    assert extraction.selected_html.count("<img") == 6
    from content_creator.services.url_video import _asset_target_count
    assert _asset_target_count(len(extraction.body)) >= 2


def test_jsonld_and_metadata_candidates_receive_unique_ids():
    payload = json.dumps({"@type": "Article", "description": "这是 JSON-LD 中的文章摘要说明，包含完整主题、使用方法、核心能力和应用范围，长度足够形成正文候选。"}, ensure_ascii=False)
    html = f"<html><head><script type='application/ld+json'>{payload}</script><meta name='description' content='这是页面 metadata 摘要，内容不同，并且完整说明产品升级结果、用户价值和后续计划，足够形成另一个候选。'></head></html>"
    soup = BeautifulSoup(html, "html.parser")
    candidates = _discover_text_candidates(html, soup, "文章标题")
    assert len(candidates) == 2
    assert len({item.id for item in candidates}) == len(candidates)


def test_plural_icons_directory_is_filtered_as_page_ui():
    candidate = AssetCandidate(
        id="asset-icon", kind=AssetKind.image,
        source_url="https://assets.example.com/icons/search.svg",
        page_url="https://example.com/article", alt="搜索",
    )
    diagnostics = {}
    assert basic_asset_filter([candidate], diagnostics) == []
    assert diagnostics["rule_filter"]["icon_avatar_logo"] == 1
