"""Safe article fetching, image extraction and deterministic editorial fallbacks."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import mimetypes
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup
from PIL import Image, ImageOps

from content_creator.schemas import ArticleBrief, ArticleImage, AssetCandidate, AssetDecision, AssetKind, ImageRole, ImageTag, TransitionContext, TransitionRelation, VideoCopy
from content_creator.services.llm.router import get_agent_provider

MAX_HTML_BYTES = 5_000_000
MAX_IMAGE_BYTES = 12_000_000
MAX_REDIRECTS = 5
MIN_IMAGE_EDGE = 180
MIN_IMAGE_PIXELS = 100_000
SCREENSHOT_SIZE = (1280, 720)
logger = logging.getLogger(__name__)
_SRCSET_PART = re.compile(r"^\s*(\S+)(?:\s+(\d+(?:\.\d+)?)([wx]))?")
_DIRECT_VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov"}
_IMAGE_EXTENSIONS = {".avif", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}
_UI_TOKEN = re.compile(r"(?:^|[-_/.])(icon|avatar|logo|wordmark|button|badge|lock|protection)(?:[-_/.]|$)", re.I)


class BrowserImportRequired(ValueError):
    """The page is public, but its origin declined automated retrieval."""

    def __init__(self, url: str, status_code: int) -> None:
        self.url = url
        self.status_code = status_code
        super().__init__(f"网页返回 HTTP {status_code}，需要通过浏览器导入页面内容")


def _assert_public_url(value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("URL 必须是公开的 HTTP 或 HTTPS 网页地址")
    try:
        addresses = {entry[4][0] for entry in socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)}
    except OSError as exc:
        raise ValueError("无法解析网页地址") from exc
    # Some legitimate public hosts publish an additional non-routable IPv6
    # placeholder. Accept the hostname only when it has at least one public
    # address; hosts resolving solely to local/private addresses stay blocked.
    if not any(ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("不允许访问本机、内网或保留地址")


def _get(client: httpx.Client, url: str, limit: int) -> httpx.Response:
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        _assert_public_url(current)
        response = client.get(current, follow_redirects=False)
        if response.is_redirect:
            location = response.headers.get("location")
            if not location:
                raise ValueError("网页重定向缺少目标地址")
            current = urljoin(current, location)
            continue
        response.raise_for_status()
        if int(response.headers.get("content-length", "0") or 0) > limit:
            raise ValueError("远程文件超过大小限制")
        if len(response.content) > limit:
            raise ValueError("远程文件超过大小限制")
        return response
    raise ValueError("网页重定向次数过多")


def _meta(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return str(tag["content"]).strip()
    return ""


def fetch_article(url: str) -> tuple[ArticleBrief, BeautifulSoup]:
    _assert_public_url(url)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; VideoAssistant/1.0)", "Accept": "text/html,application/xhtml+xml"}
    with httpx.Client(headers=headers, timeout=httpx.Timeout(15, connect=8), trust_env=True) as client:
        try:
            response = _get(client, url, MAX_HTML_BYTES)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403}:
                raise BrowserImportRequired(url, exc.response.status_code) from exc
            raise
    return parse_article_html(url, response.text, canonical_url=str(response.url), content_type=response.headers.get("content-type", ""), allow_rendered_fallback=True)


def parse_article_html(url: str, html: str, *, canonical_url: str | None = None, content_type: str = "text/html", allow_rendered_fallback: bool = False) -> tuple[ArticleBrief, BeautifulSoup]:
    """Parse supplied page HTML without accessing browser state or credentials."""
    _assert_public_url(url)
    if len(html.encode("utf-8")) > MAX_HTML_BYTES:
        raise ValueError("导入的网页 HTML 超过 5MB 限制")
    if "html" not in content_type.lower():
        raise ValueError("URL 未返回 HTML 文章页面")
    extracted, soup = _extract_article_text(html)
    if len(extracted.strip()) < 160 and allow_rendered_fallback:
        html = _rendered_html(url)
        extracted, soup = _extract_article_text(html)
    if len(extracted.strip()) < 80:
        raise ValueError("未能从网页提取足够的正文内容")
    title = _meta(soup, "og:title", "twitter:title") or (soup.title.get_text(strip=True) if soup.title else "未命名文章")
    canonical = _meta(soup, "og:url") or canonical_url or url
    site = _meta(soup, "og:site_name") or urlparse(canonical).hostname or ""
    return ArticleBrief(url=url, canonical_url=canonical, site_name=site, author=_meta(soup, "author", "article:author"), published_at=_meta(soup, "article:published_time", "date"), title=title[:500], text=extracted[:50000]), soup


def _extract_article_text(html: str) -> tuple[str, BeautifulSoup]:
    soup = BeautifulSoup(html, "html.parser")
    extracted = trafilatura.extract(html, include_comments=False, include_tables=True, output_format="txt") or ""
    if len(extracted.strip()) < 160:
        extracted = "\n".join(node.get_text(" ", strip=True) for node in soup.select("article p, main p, .article p, .content p, p"))
    return extracted, soup


def _rendered_html(url: str) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - dependency validation is external.
        raise ValueError("网页需要 JavaScript 渲染，但 Playwright 不可用") from exc
    _assert_public_url(url)
    if not chromium_available():
        raise ValueError("网页需要 JavaScript 渲染，但正文截图引擎尚未安装；请运行 make browser")
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.route("**/*", _public_route)
            page.goto(url, wait_until="networkidle", timeout=25_000)
            html = page.content()
            browser.close()
            return html
    except Exception as exc:
        raise ValueError("网页需要 JavaScript 渲染，但正文截图引擎不可用；请运行 make browser") from exc


def capture_article_screenshots(url: str, project_dir: str | Path, start_index: int, count: int, diagnostics: dict | None = None) -> list[ArticleImage]:
    """Capture distinct 16:9 regions from the cleaned article body."""
    if count <= 0:
        return []
    if not chromium_available():
        raise ValueError("正文截图引擎尚未安装；请运行 make browser")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
            page.route("**/*", _public_route)
            page.goto(url, wait_until="networkidle", timeout=25_000)
            main = _article_locator(page)
            if main is None:
                raise ValueError("无法定位文章正文区域")
            page.add_style_tag(content="header,nav,footer,aside,[role=banner],[role=navigation],.sidebar,.advert,.ads,.cookie,.cookie-banner{display:none!important}")
            main.evaluate("""element => { document.querySelectorAll('body > *').forEach(node => { if (!node.contains(element) && node !== element) node.style.display = 'none'; }); element.style.margin = '0 auto'; }""")
            box = main.bounding_box()
            if not box or box["width"] < 320 or box["height"] < 180:
                raise ValueError("文章正文区域尺寸不足")
            crop_width = min(box["width"], box["height"] * 16 / 9, 1280)
            crop_height = crop_width * 9 / 16
            left = box["x"] + max(0, (box["width"] - crop_width) / 2)
            max_top = box["y"] + max(0, box["height"] - crop_height)
            page_size = page.evaluate("() => ({scrollWidth: document.documentElement.scrollWidth, scrollHeight: document.documentElement.scrollHeight})")
            output = Path(project_dir) / "article_downloads"
            result: list[ArticleImage] = []
            hashes: list[int] = []
            positions = [box["y"] + (max_top - box["y"]) * index / max(1, count - 1) for index in range(count)]
            if diagnostics is not None:
                diagnostics.setdefault("screenshot_fallback", {}).update({"page_size": page_size, "article_box": box, "clips": [{"x": left, "y": top, "width": crop_width, "height": crop_height, "right": left + crop_width, "bottom": top + crop_height} for top in positions]})
            for top in positions:
                target = output / f"screenshot-{len(result):03d}.jpg"
                page.screenshot(path=str(target), type="jpeg", quality=88, clip={"x": left, "y": top, "width": crop_width, "height": crop_height})
                _normalize_screenshot(target)
                digest = hashlib.sha256(target.read_bytes()).hexdigest()
                perceptual = _perceptual_hash(target)
                if any(_hamming_distance(perceptual, previous) <= 4 for previous in hashes):
                    target.unlink(missing_ok=True)
                    continue
                hashes.append(perceptual)
                result.append(ArticleImage(id=f"article-{start_index + len(result):03d}", source_url=url, local_path=str(target), width=SCREENSHOT_SIZE[0], height=SCREENSHOT_SIZE[1], source_index=start_index + len(result), alt="文章正文截图", caption="", context="正文截图", sha256=digest))
            browser.close()
            if len(result) < count:
                raise ValueError("正文截图内容重复，无法补足镜头")
            return result
    except Exception as exc:
        raise ValueError(f"文章图片少于 4 张，且无法生成正文截图：{exc}") from exc


def chromium_available() -> bool:
    try:
        completed = subprocess.run([sys.executable, "-m", "playwright", "install", "--list"], check=False, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0 and "chromium-" in completed.stdout


def _article_locator(page):
    candidates = []
    for selector in ("article", "main", "[role=main]", ".article", ".article-content", ".post-content", ".entry-content", ".mw-parser-output"):
        locator = page.locator(selector).first
        try:
            box = locator.bounding_box()
            if box and box["width"] >= 320 and box["height"] >= 180:
                candidates.append((box["width"] * box["height"], locator))
        except Exception:
            continue
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def _normalize_screenshot(path: Path) -> None:
    with Image.open(path).convert("RGB") as image:
        ImageOps.fit(image, SCREENSHOT_SIZE, Image.Resampling.LANCZOS, centering=(0.5, 0.5)).save(path, "JPEG", quality=90, optimize=True)


def _perceptual_hash(path: Path) -> int:
    with Image.open(path).convert("L").resize((8, 8), Image.Resampling.LANCZOS) as image:
        values = list(image.getdata())
    average = sum(values) / len(values)
    return sum((1 << index) for index, value in enumerate(values) if value >= average)


def _hamming_distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def _srcset_urls(value: str) -> list[str]:
    parsed: list[tuple[str, int]] = []
    for part in value.split(","):
        match = _SRCSET_PART.match(part)
        if match:
            descriptor = match.group(3)
            score = int(float(match.group(2) or 0) * (1080 if descriptor == "x" else 1))
            parsed.append((match.group(1), score))
    if not parsed:
        return []
    # A 1080px stage does not benefit from arbitrarily large originals. Prefer
    # the largest candidate at or below 1920px, otherwise use the smallest above it.
    below = [item for item in parsed if item[1] and item[1] <= 1920]
    return [max(below, key=lambda item: item[1])[0] if below else min(parsed, key=lambda item: item[1] or 10**9)[0]]


def discover_asset_candidates(soup: BeautifulSoup, brief: ArticleBrief) -> tuple[list[AssetCandidate], dict]:
    """Discover every supported asset URL before any download or model call."""
    counts = {"html_img": len(soup.find_all("img")), "src": 0, "srcset": 0, "picture_source": 0, "og_image": 0, "svg": 0, "video": 0}
    raw: list[dict] = []

    def context_for(node, index: int) -> tuple[str, str, str]:
        parent = node.find_parent(["figure", "article", "section", "p", "div"])
        nearby = parent.get_text(" ", strip=True)[:2000] if parent else ""
        figure = node.find_parent("figure")
        caption_node = figure.find("figcaption") if figure else None
        return str(node.get("alt", ""))[:600], (caption_node.get_text(" ", strip=True) if caption_node else "")[:1000], nearby

    def add(value: object, source_type: str, node, index: int, kind: AssetKind = AssetKind.image) -> None:
        if not value or str(value).startswith("data:"):
            return
        absolute = urljoin(brief.canonical_url, str(value))
        alt, caption, nearby = context_for(node, index)
        raw.append({"url": absolute, "source_type": source_type, "alt": alt, "caption": caption, "nearby": nearby, "index": index, "kind": kind})

    for index, image in enumerate(soup.find_all("img")):
        if image.get("src"):
            counts["src"] += 1
        if image.get("srcset"):
            counts["srcset"] += 1
            sources = _srcset_urls(str(image["srcset"]))
            # Wikimedia often advertises a full original as its 2x candidate.
            # Keep the page's thumbnail when it is already a sensible raster size
            # instead of downloading an unbounded original and hitting rate limits.
            source = sources[0] if sources else None
            if source and "/thumb/" not in source and "/thumb/" in str(image.get("src", "")):
                source = str(image["src"])
            if source:
                add(source, "srcset", image, index)
        else:
            for attribute, source_type in (("data-src", "data-src"), ("data-original", "data-original"), ("src", "src")):
                if image.get(attribute):
                    add(image.get(attribute), source_type, image, index)
                    break

    for index, source in enumerate(soup.select("picture source[src], picture source[srcset]"), start=counts["html_img"]):
        counts["picture_source"] += 1
        if source.get("src"):
            add(source.get("src"), "picture/source", source, index)
        if source.get("srcset"):
            for value in _srcset_urls(str(source["srcset"])):
                add(value, "picture/source", source, index)

    for meta_name in ("og:image", "twitter:image"):
        for tag in soup.select(f'meta[property="{meta_name}"], meta[name="{meta_name}"]'):
            if tag.get("content"):
                counts["og_image"] += 1
                add(tag["content"], meta_name, tag, len(raw))
    for index, video in enumerate(soup.select("video[src], video source[src]")):
        if video.get("src"):
            counts["video"] += 1
            add(video["src"], "video", video, index, AssetKind.video)
        for source in video.select("source[src]"):
            counts["video"] += 1
            add(source["src"], "video/source", source, index, AssetKind.video)
    for meta_name in ("og:video", "og:video:url", "og:video:secure_url"):
        for tag in soup.select(f'meta[property="{meta_name}"], meta[name="{meta_name}"]'):
            if tag.get("content"):
                counts["video"] += 1
                add(tag["content"], meta_name, tag, len(raw), AssetKind.video)
    for index, frame in enumerate(soup.select("iframe[src]")):
        add(frame["src"], "iframe", frame, index, AssetKind.embedded_video)

    merged: dict[tuple[AssetKind, str], AssetCandidate] = {}
    for item in raw:
        key = (item["kind"], item["url"])
        if key in merged:
            if item["source_type"] not in merged[key].source_types:
                merged[key].source_types.append(item["source_type"])
            continue
        suffix = Path(urlparse(item["url"]).path).suffix.lower()
        # Wikimedia raster thumbnails retain the original SVG name in their
        # path (for example ``...Diagram.svg/960px-Diagram.svg.png``). They
        # are PNG responses and must remain usable image candidates.
        is_svg = suffix == ".svg"
        if is_svg:
            counts["svg"] += 1
        merged[key] = AssetCandidate(id=f"asset-{len(merged):03d}", kind=item["kind"], source_url=item["url"], page_url=brief.canonical_url, section_index=item["index"], original_index=item["index"], source_types=[item["source_type"]], alt=item["alt"], caption=item["caption"], nearby_text=item["nearby"], mime_type=mimetypes.guess_type(item["url"])[0] or "", is_svg=is_svg)
    diagnostics = {"asset_discovery": {**counts, "before_dedup": len(raw), "after_dedup": len(merged), "embedded_video": sum(item.kind == AssetKind.embedded_video for item in merged.values())}}
    return list(merged.values()), diagnostics


def basic_asset_filter(candidates: list[AssetCandidate], diagnostics: dict) -> list[AssetCandidate]:
    reasons = {"size": 0, "mime": 0, "icon_avatar_logo": 0, "format": 0, "other": 0}
    rejected: list[dict] = []
    kept: list[AssetCandidate] = []
    for candidate in candidates:
        parsed = urlparse(candidate.source_url)
        reason = ""
        suffix = Path(parsed.path).suffix.lower()
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            reason = "other"
        elif candidate.kind == AssetKind.image and _UI_TOKEN.search(f"{parsed.path} {candidate.alt}"):
            reason = "icon_avatar_logo"
        elif candidate.kind == AssetKind.video and suffix and suffix not in _DIRECT_VIDEO_EXTENSIONS:
            reason = "format"
        elif candidate.kind == AssetKind.image and suffix and suffix not in _IMAGE_EXTENSIONS and not candidate.is_svg:
            reason = "format"
        if reason:
            reasons[reason] += 1
            rejected.append({"asset_id": candidate.id, "reason": reason, "source_url": candidate.source_url})
        else:
            kept.append(candidate)
    diagnostics["rule_filter"] = {**reasons, "remaining": len(kept), "rejected": rejected}
    return kept


def _local_asset_decisions(candidates: list[AssetCandidate]) -> list[AssetDecision]:
    def priority(item: AssetCandidate) -> tuple[bool, bool, bool, int]:
        suffix = Path(urlparse(item.source_url).path).suffix.lower()
        return (item.kind != AssetKind.image, item.is_svg, suffix == ".gif", item.original_index)

    ordered = sorted(candidates, key=priority)
    chosen = {item.id for item in ordered[:6]}
    return [AssetDecision(asset_id=item.id, selected=item.id in chosen, role=ImageRole.hero if item.id in chosen and item.original_index == min((choice.original_index for choice in ordered[:6]), default=0) else ImageRole.evidence, topics=item.alt.split()[:4], relevance=0.8 if item.id in chosen else 0.1, visual_quality=0.6, reason="deterministic article-order fallback") for item in candidates]


def select_assets_with_agent(brief: ArticleBrief, candidates: list[AssetCandidate], diagnostics: dict) -> list[AssetDecision]:
    fallback = _local_asset_decisions(candidates)
    diagnostics["asset_agent"] = {"sent": len(candidates), "mode": "local_fallback", "selected": 0, "decisions": []}
    if not candidates:
        return fallback
    provider = get_agent_provider("asset")
    if provider.model_name == "mock":
        decisions = fallback
    else:
        prompt = json.dumps({"task": "选择与文章最相关、适合短视频的网页素材。只能引用 input asset_id；不得生成 URL。返回 JSON。", "article": {"title": brief.title, "text": brief.text[:9000]}, "assets": [item.model_dump(mode="json") for item in candidates], "output": {"asset_decisions": [{"asset_id": "input asset id", "selected": True, "role": "hero|overview|evidence|data|diagram|demo|product|quote|result|portrait|brand|other|irrelevant", "topics": ["string"], "entities": ["string"], "relevance": "0..1", "visual_quality": "0..1", "reason": "short reason"}]}}, ensure_ascii=False)
        try:
            raw = provider.complete_json(prompt)
            parsed = [AssetDecision.model_validate(item) for item in json.loads(raw)["asset_decisions"]]
            if {item.asset_id for item in parsed} != {item.id for item in candidates}:
                raise ValueError("asset agent returned incomplete or unknown asset IDs")
            decisions = parsed
            diagnostics["asset_agent"]["mode"] = "text_fallback"
        except Exception as exc:
            diagnostics["asset_agent"]["error"] = f"{type(exc).__name__}: {exc}"
            decisions = fallback
    diagnostics["asset_agent"].update({"selected": sum(item.selected for item in decisions), "decisions": [item.model_dump(mode="json") for item in decisions if item.selected]})
    return decisions


def _extension_for(content_type: str, candidate: AssetCandidate) -> str:
    if candidate.is_svg or "svg" in content_type:
        return ".svg"
    return {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif", "image/avif": ".avif", "video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov"}.get(content_type.split(";", 1)[0], Path(urlparse(candidate.source_url).path).suffix.lower() or ".bin")


def _download_with_retry(client: httpx.Client, url: str, limit: int) -> httpx.Response:
    for attempt in range(3):
        try:
            return _get(client, url, limit)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 429 or attempt == 2:
                raise
            retry_after = exc.response.headers.get("retry-after", "")
            try:
                delay = min(8.0, max(1.0, float(retry_after)))
            except ValueError:
                delay = float(2 ** attempt)
            time.sleep(delay)
    raise RuntimeError("unreachable")


def download_selected_assets(candidates: list[AssetCandidate], decisions: list[AssetDecision], project_dir: str | Path, diagnostics: dict, *, browser_imported: bool = False) -> list[ArticleImage]:
    by_id = {candidate.id: candidate for candidate in candidates}
    selected = [by_id[item.asset_id] for item in decisions if item.selected and item.asset_id in by_id]
    source_dir = Path(project_dir) / "materials" / "images"
    source_dir.mkdir(parents=True, exist_ok=True)
    stats = {"attempted": 0, "succeeded": 0, "failed": 0, "browser_asset_required": 0, "svg": 0, "jpeg": 0, "png": 0, "webp": 0, "other": 0, "items": []}
    assets: list[ArticleImage] = []
    hashes: set[str] = set()
    perceptual_hashes: list[int] = []
    headers = {"User-Agent": "Mozilla/5.0 (compatible; VideoAssistant/1.0)", "Accept": "image/avif,image/webp,image/*,video/*;q=0.8,*/*;q=0.1"}
    with httpx.Client(headers=headers, timeout=httpx.Timeout(20, connect=8), trust_env=True) as client:
        for index, item in enumerate(selected):
            stats["attempted"] += 1
            target: Path | None = None
            record = {"asset_id": item.id, "source_url": item.source_url, "status": "failed"}
            try:
                response = _download_with_retry(client, item.source_url, MAX_IMAGE_BYTES)
                content_type = response.headers.get("content-type", "").lower()
                if item.kind == AssetKind.image and not content_type.startswith("image/"):
                    raise ValueError("mime_not_image")
                if item.kind == AssetKind.video and not content_type.startswith("video/"):
                    raise ValueError("mime_not_video")
                digest = hashlib.sha256(response.content).hexdigest()
                if digest in hashes:
                    raise ValueError("duplicate_sha256")
                suffix = _extension_for(content_type, item)
                target = source_dir / f"{index:03d}-{item.id}{suffix}"
                target.write_bytes(response.content)
                bucket = "svg" if suffix == ".svg" else "jpeg" if suffix in {".jpg", ".jpeg"} else "png" if suffix == ".png" else "webp" if suffix == ".webp" else "other"
                stats[bucket] += 1
                if suffix == ".svg":
                    record.update({"status": "svg_rasterization_unavailable", "local_path": str(target), "mime_type": content_type})
                    stats["succeeded"] += 1
                    hashes.add(digest)
                    stats["items"].append(record)
                    continue
                if item.kind != AssetKind.image:
                    record.update({"status": "downloaded_video", "local_path": str(target), "mime_type": content_type})
                    stats["succeeded"] += 1
                    hashes.add(digest)
                    stats["items"].append(record)
                    continue
                with Image.open(target) as image:
                    image.verify()
                with Image.open(target) as image:
                    width, height = image.size
                if min(width, height) < MIN_IMAGE_EDGE or width * height < MIN_IMAGE_PIXELS:
                    raise ValueError("image_too_small")
                perceptual = _perceptual_hash(target)
                # Sparse black-and-white diagrams often share a coarse 8x8 hash
                # without being duplicate visuals. SHA-256 handles exact copies;
                # reserve perceptual de-duplication for near-identical variants.
                if any(_hamming_distance(perceptual, previous) <= 1 for previous in perceptual_hashes):
                    raise ValueError("duplicate_perceptual")
                hashes.add(digest)
                perceptual_hashes.append(perceptual)
                assets.append(ArticleImage(id=f"article-{len(assets):03d}", source_url=item.source_url, local_path=str(target), width=width, height=height, source_index=item.original_index, alt=item.alt, caption=item.caption, context=item.nearby_text, sha256=digest))
                record.update({"status": "downloaded", "local_path": str(target), "mime_type": content_type, "width": width, "height": height})
                stats["succeeded"] += 1
            except httpx.HTTPStatusError as exc:
                if target is not None:
                    target.unlink(missing_ok=True)
                if browser_imported and exc.response.status_code in {401, 403}:
                    record.update({"status": "browser_asset_required", "http_status": exc.response.status_code, "local_path": None, "error": str(exc)})
                    stats["browser_asset_required"] += 1
                else:
                    record.update({"http_status": exc.response.status_code, "error": str(exc)})
                    stats["failed"] += 1
            except (httpx.HTTPError, OSError, ValueError, Image.DecompressionBombError) as exc:
                if target is not None:
                    target.unlink(missing_ok=True)
                record["error"] = str(exc)
                stats["failed"] += 1
            stats["items"].append(record)
    diagnostics["downloader"] = stats
    return assets


def log_asset_diagnostics(diagnostics: dict) -> None:
    for label, key in (("Asset Discovery", "asset_discovery"), ("Rule Filter", "rule_filter"), ("Asset Agent", "asset_agent"), ("Downloader", "downloader"), ("Project Compile", "project_compile"), ("Screenshot Fallback", "screenshot_fallback")):
        if key in diagnostics:
            logger.warning("[%s] %s", label, json.dumps(diagnostics[key], ensure_ascii=False, default=str))


def download_article_images(soup: BeautifulSoup, brief: ArticleBrief, project_dir: str | Path) -> list[ArticleImage]:
    """Compatibility wrapper for callers outside the URL pipeline."""
    candidates, diagnostics = discover_asset_candidates(soup, brief)
    filtered = basic_asset_filter(candidates, diagnostics)
    decisions = _local_asset_decisions(filtered)
    return download_selected_assets(filtered, decisions, project_dir, diagnostics)


def _public_route(route) -> None:
    try:
        _assert_public_url(route.request.url)
        route.continue_()
    except ValueError:
        route.abort()


def _fallback_tag(image: ArticleImage) -> ImageTag:
    text = f"{image.alt} {image.caption} {image.context}".lower()
    role = ImageRole.data if any(word in text for word in ("chart", "data", "数据", "图表")) else ImageRole.demo if any(word in text for word in ("demo", "界面", "截图", "screen")) else ImageRole.hero if image.source_index == 0 else ImageRole.evidence
    return ImageTag(image_id=image.id, role=role, topics=[word for word in image.alt.split()[:4]], salience=0.9 if role == ImageRole.hero else 0.6, visual_quality=min(1.0, image.width * image.height / 2_000_000), section_index=image.source_index)


def tag_images(brief: ArticleBrief, images: list[ArticleImage]) -> tuple[ArticleBrief, VideoCopy, list[ImageTag]]:
    provider = get_agent_provider("asset")
    fallback_copy = VideoCopy(headline=brief.title[:80], subtitle=(brief.site_name or "文章要点")[:40], body=brief.text[:180])
    fallback_tags = [_fallback_tag(image) for image in images]
    if provider.model_name == "mock":
        return brief.model_copy(update={"summary": fallback_copy.body, "topics": fallback_tags[0].topics}), fallback_copy, fallback_tags
    payload = {"title": brief.title, "site": brief.site_name, "text": brief.text[:9000], "images": [{"id": image.id, "alt": image.alt, "caption": image.caption, "context": image.context[:800], "size": [image.width, image.height]} for image in images]}
    prompt = json.dumps({"task": "阅读文章并生成短视频文案和图片标签。只返回 JSON。", "article": payload, "output": {"summary": "<=1200 chars", "topics": ["string"], "mood": "string", "video_copy": {"headline": "<=80 chars, <=2 lines", "subtitle": "<=40 chars, <=2 lines", "body": "<=400 chars, <=8 lines"}, "image_tags": [{"image_id": "input id", "role": "hero|overview|evidence|data|demo|product|quote|result|brand|other", "topics": ["string"], "entities": ["string"], "salience": "0..1", "visual_quality": "0..1", "section_index": "int"}]}}, ensure_ascii=False)
    try:
        multimodal = getattr(provider, "complete_multimodal", None)
        if callable(multimodal):
            try:
                raw = multimodal(prompt, [image.local_path for image in images])
            except Exception:
                raw = provider.complete_json(prompt)
        else:
            raw = provider.complete_json(prompt)
        result = json.loads(raw)
        tags = [ImageTag.model_validate(item) for item in result["image_tags"]]
        if {tag.image_id for tag in tags} != {image.id for image in images}:
            raise ValueError("incomplete image tags")
        updated = brief.model_copy(update={"summary": str(result.get("summary", ""))[:1200], "topics": list(result.get("topics", []))[:12], "mood": str(result.get("mood", "informative"))[:40]})
        return updated, VideoCopy.model_validate(result["video_copy"]), tags
    except Exception:
        return brief.model_copy(update={"summary": fallback_copy.body, "topics": fallback_tags[0].topics}), fallback_copy, fallback_tags


def order_images(images: list[ArticleImage], tags: list[ImageTag]) -> tuple[list[ArticleImage], list[TransitionContext]]:
    by_id = {tag.image_id: tag for tag in tags}
    ranked = sorted(images, key=lambda image: (-by_id[image.id].salience, image.source_index))[:6]
    first = min(ranked, key=lambda image: (0 if by_id[image.id].role in {ImageRole.hero, ImageRole.overview} else 1, image.source_index))
    last = min(ranked, key=lambda image: (0 if by_id[image.id].role in {ImageRole.result, ImageRole.brand, ImageRole.product} else 1, -by_id[image.id].salience, image.source_index))
    middle = sorted((image for image in ranked if image.id not in {first.id, last.id}), key=lambda image: image.source_index)
    ordered = [first, *middle]
    if last.id != first.id:
        ordered.append(last)
    contexts = [TransitionContext(from_image_id=current.id, to_image_id=nxt.id, relation=TransitionRelation.climax if index == len(ordered) - 2 else TransitionRelation.continuation, strength=0.9 if index == len(ordered) - 2 else 0.55) for index, (current, nxt) in enumerate(zip(ordered, ordered[1:]))]
    return ordered, contexts
