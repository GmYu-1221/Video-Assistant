"""Safe article fetching, image extraction and deterministic editorial fallbacks."""
from __future__ import annotations

import hashlib
import html as html_escape
import ipaddress
import json
import logging
import mimetypes
import os
import re
import socket
import subprocess
import sys
import time
import tempfile
from difflib import SequenceMatcher
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlsplit, urlunsplit

import httpx
import trafilatura
from bs4 import BeautifulSoup
from PIL import Image, ImageOps

from content_creator.schemas import (
    ArticleBrief, ArticleExtractionResult, ArticleImage, ArticleImageTaggingDecision, ArticleSelectionDecision,
    ArticleTextCandidate, AssetCandidate, AssetDecision, AssetKind,
    AssetSelectionDecision, CandidatePreview, CandidateVisualAnalysisDecision,
    CandidateVisualProfile, ImageHeadlineBatchDecision, ImageRole, ImageTag, TransitionContext,
    TransitionRelation, VideoCopy,
)
from content_creator.services.llm.router import get_agent_provider
from content_creator.services.structured_agent import StructuredAgentRunner, issue

MAX_HTML_BYTES = 5_000_000
MAX_IMAGE_BYTES = 12_000_000
MAX_REDIRECTS = 5
MIN_IMAGE_EDGE = 180
MIN_IMAGE_PIXELS = 100_000
SCREENSHOT_SIZE = (1280, 720)
ARTICLE_SCREENSHOT_LIMIT = 1
CANDIDATE_THUMBNAIL_LIMIT = 24
CANDIDATE_THUMBNAIL_EDGE = 512
CANDIDATE_VISION_BATCH_SIZE = 6
logger = logging.getLogger(__name__)


def _agent_artifact_root(value: str | Path | None) -> Path:
    return Path(value) if value is not None else Path(tempfile.gettempdir()) / "video-assistant-agent-runs" / str(os.getpid())
_SRCSET_PART = re.compile(r"^\s*(\S+)(?:\s+(\d+(?:\.\d+)?)([wx]))?")
_DIRECT_VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov"}
_IMAGE_EXTENSIONS = {".avif", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}
_UI_TOKEN = re.compile(r"(?:^|[-_/.])(icons?|avatar|logo|wordmark|button|badge|lock|protection|toolbar|tobar|heart|thumb|collect|comment|share|wechat|weixin|alipay|pay|reward|vip|close|coupon|follow|like|unlike)(?:[-_/.]|$)", re.I)
_UI_SUBSTRING = re.compile(r"(?:toolbar|tobar|heart|thumb|collect|comment|share|wechat|weixin|alipay|reward|vip|coupon|follow|like|unlike|identityvip|identity|readcount|pay-help|guide-red)", re.I)
_UI_TEXT_TOKEN = re.compile(r"(?:用户.{0,12}主页|个人主页|头像|profile picture|author avatar)", re.I)
_QR_TOKEN = re.compile(
    r"(?:^|[-_/.])(?:qr|qrcode|qr-code|barcode|share[-_]?code|scan[-_]?code|"
    r"new_qr_img|qrcode_img|qrcode_image)(?:[-_/.?]|$)", re.I,
)
_QR_TEXT_TOKEN = re.compile(r"(?:二维码|扫描二维码|扫码下载|分享码|下载码|scan\s*(?:this\s*)?code)", re.I)
_PARTNER_UI_TOKEN = re.compile(
    r"(?:合作伙伴|合作品牌|友情链接|广告|app\s*下载|下载客户端|copyright|powered\s*by|"
    r"阿里云|火山引擎|高德|个推|partner|sponsor|footer)", re.I,
)
_EDITORIAL_SIGNAL = re.compile(
    r"(?:图表|数据|趋势|营收|销量|报告|统计|架构|流程|示意|产品|界面|代码|"
    r"chart|diagram|dashboard|screenshot|interface|architecture|workflow|data|trend)", re.I,
)
_ARTICLE_UI_PHRASES = {
    "notifications", "notification settings", "fork", "star", "code", "issues",
    "pull requests", "actions", "projects", "security and quality", "insights",
    "branches", "tags", "open more actions menu", "folders and files", "last commit",
    "latest commit", "history", "repository files navigation", "table of contents",
    "about", "resources", "watchers", "releases", "packages", "used by",
    "contributors", "languages", "uh oh", "there was an error while loading",
    "you must be signed in to change notification settings",
}
_ARTICLE_UI_ATTR = re.compile(r"(?:^|[-_])(nav|navigation|breadcrumb|sidebar|toolbar|header|footer|repo[-_]?nav|file[-_]?list|repository[-_]?files|action[-_]?menu)(?:$|[-_])", re.I)


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
    extraction, soup = fetch_article_with_extraction(url)
    return _brief_from_extraction(extraction), soup


def fetch_article_with_extraction(url: str, *, agent_artifact_dir: str | Path | None = None) -> tuple[ArticleExtractionResult, BeautifulSoup]:
    _assert_public_url(url)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; VideoAssistant/1.0)", "Accept": "text/html,application/xhtml+xml"}
    with httpx.Client(headers=headers, timeout=httpx.Timeout(15, connect=8), trust_env=True) as client:
        try:
            response = _get(client, url, MAX_HTML_BYTES)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403}:
                raise BrowserImportRequired(url, exc.response.status_code) from exc
            raise
    return extract_article_html(url, response.text, canonical_url=str(response.url), effective_base_url=str(response.url), content_type=response.headers.get("content-type", ""), allow_rendered_fallback=True, agent_artifact_dir=agent_artifact_dir)


def parse_article_html(url: str, html: str, *, canonical_url: str | None = None, content_type: str = "text/html", allow_rendered_fallback: bool = False) -> tuple[ArticleBrief, BeautifulSoup]:
    """Compatibility wrapper that keeps the public ArticleBrief API stable."""
    extraction, soup = extract_article_html(url, html, canonical_url=canonical_url, content_type=content_type, allow_rendered_fallback=allow_rendered_fallback)
    return _brief_from_extraction(extraction), soup


def extract_article_html(url: str, html: str, *, canonical_url: str | None = None, effective_base_url: str | None = None, content_type: str = "text/html", allow_rendered_fallback: bool = False, agent_artifact_dir: str | Path | None = None) -> tuple[ArticleExtractionResult, BeautifulSoup]:
    """Extract article text through local candidates and an ID-only LLM decision."""
    _assert_public_url(url)
    if len(html.encode("utf-8")) > MAX_HTML_BYTES:
        raise ValueError("导入的网页 HTML 超过 5MB 限制")
    if "html" not in content_type.lower():
        raise ValueError("URL 未返回 HTML 文章页面")
    soup = BeautifulSoup(html, "html.parser")
    canonical = _trusted_canonical_url(url, _meta(soup, "og:url") or canonical_url)
    base = effective_base_url or url
    title = _meta(soup, "og:title", "twitter:title") or (soup.title.get_text(strip=True) if soup.title else "未命名文章")
    candidates = _deduplicate_text_candidates(_discover_text_candidates(html, soup, title))
    selected, diagnostics = _select_article_candidates(candidates, title, artifact_dir=agent_artifact_dir)
    if not _quality_ok(selected.body) and allow_rendered_fallback:
        rendered = _rendered_html(url)
        rendered_soup = BeautifulSoup(rendered, "html.parser")
        rendered_candidates = _deduplicate_text_candidates(_discover_text_candidates(rendered, rendered_soup, title, source_override="rendered_dom", start_index=len(candidates)))
        candidates = _deduplicate_text_candidates(candidates + rendered_candidates)
        selected, diagnostics = _select_article_candidates(candidates, title, artifact_dir=agent_artifact_dir, contract_name="article_selection_rendered")
        soup = rendered_soup if selected.extraction_method == "rendered_dom" else soup
    if not _quality_ok(selected.body):
        raise ValueError(f"未能从网页提取足够的正文内容（候选 {len(candidates)} 个，最终 {len(selected.body)} 字）")
    diagnostics["candidate_total"] = len(candidates)
    _, cleanup_stats = _clean_article_fragment(html)
    diagnostics["html_cleanup"] = {
        "raw_chars": len(_normalize_text(soup.get_text(" ", strip=True))),
        "cleaned_chars": len(selected.body),
        "raw_paragraph_count": len(soup.find_all(["p", "h2", "h3", "li", "pre", "blockquote"])),
        "cleaned_paragraph_count": len([line for line in selected.body.splitlines() if _normalize_text(line)]),
        "ui_nodes_removed": cleanup_stats["ui_nodes_removed"],
        "structural_nodes_removed": cleanup_stats["structural_nodes_removed"],
        "ui_token_hits": cleanup_stats["ui_token_hits"],
        "selected_html_is_clean": True,
    }
    selected = selected.model_copy(update={"canonical_url": canonical, "effective_base_url": base, "requested_url": url})
    selected = selected.model_copy(update={"diagnostics": diagnostics})
    return selected, soup


def _brief_from_extraction(extraction: ArticleExtractionResult) -> ArticleBrief:
    return ArticleBrief(url=extraction.requested_url, requested_url=extraction.requested_url, canonical_url=extraction.canonical_url, effective_base_url=extraction.effective_base_url, title=extraction.title[:500], text=extraction.body[:50000])


def augment_soup_with_selected_html(soup: BeautifulSoup, selected_html: str) -> BeautifulSoup:
    """Expose selected inert article markup to Asset Discovery without scripts."""
    if not selected_html:
        return soup
    augmented = BeautifulSoup(str(soup), "html.parser")
    fragment = BeautifulSoup(selected_html, "html.parser")
    for node in fragment.select("script, iframe, object, embed, noscript"):
        node.decompose()
    target = augmented.body or augmented
    target.append(fragment)
    return augmented


def _trusted_canonical_url(requested_url: str, candidate: str | None) -> str:
    """Accept canonical metadata only when it is a sane same-origin page hint."""
    if not candidate:
        return requested_url
    requested = urlsplit(requested_url)
    parsed = urlsplit(candidate)
    invalid = (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or "undefined" in parsed.path.lower().split("/")
        or parsed.hostname.lower() != (requested.hostname or "").lower()
    )
    if invalid:
        return requested_url
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))


def _extract_article_text(html: str) -> tuple[str, BeautifulSoup]:
    soup = BeautifulSoup(html, "html.parser")
    extracted = trafilatura.extract(html, include_comments=False, include_tables=True, output_format="txt") or ""
    if len(extracted.strip()) < 160:
        extracted = "\n".join(node.get_text(" ", strip=True) for node in soup.select("article p, main p, .article p, .content p, p"))
    return extracted, soup


_SCRIPT_ASSIGNMENT = re.compile(r"(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*(['\"])", re.S)
_TEXT_SELECTORS = (
    "article", "main", "[role=main]", "[itemprop='articleBody']",
    ".article", ".article-content", ".post-content", ".post-body", ".postBody",
    ".blogpost-body", ".entry-content", ".content", ".text_area", ".content_area",
)
_METADATA_SOURCES = {"metadata", "jsonld"}


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", html_escape.unescape(value or "")).strip()


def _article_ui_match(node) -> tuple[bool, list[str]]:
    """Identify page chrome without treating every short README line as UI."""
    text = _normalize_text(node.get_text(" ", strip=True))
    lowered = text.casefold()
    attrs = " ".join(str(node.get(name, "")) for name in ("id", "class", "aria-label", "data-testid"))
    attr_match = bool(_ARTICLE_UI_ATTR.search(attrs))
    hits = [
        phrase for phrase in _ARTICLE_UI_PHRASES
        if (re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", lowered) if " " not in phrase else phrase in lowered)
    ]
    exact_ui = lowered in _ARTICLE_UI_PHRASES and (
        node.name in {"a", "button", "span", "li"} or attr_match or "error" in lowered
    )
    short_stat = len(text) <= 100 and bool(re.search(r"(?:fork|star|watchers|releases|packages|used by)\b", lowered))
    links = node.find_all("a")
    link_text_chars = sum(len(_normalize_text(link.get_text(" ", strip=True))) for link in links)
    link_cluster = (
        len(links) >= 4
        and len(text) <= 1200
        and link_text_chars / max(len(text), 1) >= .55
        and not node.find("p")
    )
    # A long paragraph may legitimately mention one of these words. Only
    # remove phrase matches when the node itself is a short UI item or carries
    # a navigation/file-list semantic attribute.
    remove = attr_match or exact_ui or short_stat or link_cluster or (len(text) <= 180 and len(hits) >= 2)
    return remove, hits


def _clean_article_fragment(fragment_html: str, *, strip_network_attrs: bool = False) -> tuple[BeautifulSoup, dict]:
    """Strip executable/network markup and obvious page chrome from HTML."""
    fragment = BeautifulSoup(fragment_html or "", "html.parser")
    stats = {"ui_nodes_removed": 0, "ui_token_hits": [], "structural_nodes_removed": 0}
    structural = fragment.select("script, iframe, object, embed, noscript, nav, header, footer, aside, button, [role='navigation'], [aria-label='Breadcrumbs']")
    for node in structural:
        node.decompose()
        stats["structural_nodes_removed"] += 1
    # Classify before mutating. GitHub-like controls often split "Star" and
    # "104k" into siblings; removing only the label would leave the count.
    classified = [(node, *_article_ui_match(node)) for node in fragment.find_all(True)]
    for node, remove, hits in classified:
        if not node.parent:
            continue
        if remove and node.name not in {"article", "main"}:
            node.decompose()
            stats["ui_nodes_removed"] += 1
            stats["ui_token_hits"].extend(hits)
    for node in fragment.find_all(True):
        for attribute in list(node.attrs):
            if attribute.lower().startswith("on"):
                del node.attrs[attribute]
            elif strip_network_attrs and attribute.lower() in {"src", "srcset", "data-src", "data-original", "href", "action", "poster"}:
                del node.attrs[attribute]
    stats["ui_token_hits"] = sorted(set(stats["ui_token_hits"]))
    return fragment, stats


def _decode_static_script_string(value: str) -> str:
    # Decode only inert string escapes. Never evaluate JavaScript or JSON code.
    value = value.replace("\\/", "/").replace("\\'", "'").replace('\\"', '"').replace("\\n", "\n").replace("\\r", "\n").replace("\\t", "\t").replace("\\\\", "\\")
    value = re.sub(r"\\u([0-9a-fA-F]{4})", lambda match: chr(int(match.group(1), 16)), value)
    value = re.sub(r"\\x([0-9a-fA-F]{2})", lambda match: chr(int(match.group(1), 16)), value)
    return html_escape.unescape(value)


def _candidate_from_html(candidate_id: str, source: str, key: str, fragment_html: str, title: str, section: int) -> ArticleTextCandidate | None:
    if not fragment_html or len(fragment_html) > MAX_HTML_BYTES:
        return None
    fragment, _ = _clean_article_fragment(fragment_html)
    text = _normalize_text(fragment.get_text(" ", strip=True))
    paragraphs = [node for node in fragment.find_all(["p", "h2", "h3", "li"]) if _normalize_text(node.get_text(" ", strip=True))]
    if len(text) < 40:
        return None
    return ArticleTextCandidate(id=candidate_id, source=source, selector_or_key=key, text=text, html=str(fragment), title_context=title[:500], section_index=section, char_count=len(text), paragraph_count=len(paragraphs), image_count=len(fragment.find_all("img")))


def _discover_text_candidates(raw_html: str, soup: BeautifulSoup, title: str, *, source_override: str | None = None, start_index: int = 0) -> list[ArticleTextCandidate]:
    candidates: list[ArticleTextCandidate] = []
    index = start_index
    for selector in _TEXT_SELECTORS:
        for node in soup.select(selector)[:4]:
            candidate = _candidate_from_html(f"text-{index:03d}", source_override or "dom", selector, str(node), title, index)
            if candidate:
                candidates.append(candidate)
                index += 1
    # JSON-LD is parsed as data, never executed.
    def walk_json(value, key_path: str = ""):
        nonlocal index
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"articleBody", "description"} and isinstance(child, str):
                    candidate = _candidate_from_html(f"text-{index:03d}", "jsonld", f"{key_path}.{key}", f"<article><p>{html_escape.escape(child)}</p></article>", title, index)
                    if candidate:
                        candidates.append(candidate)
                        index += 1
                walk_json(child, f"{key_path}.{key}")
        elif isinstance(value, list):
            for offset, child in enumerate(value):
                walk_json(child, f"{key_path}[{offset}]")
    for node in soup.select('script[type="application/ld+json"]'):
        try:
            walk_json(json.loads(node.string or node.get_text()))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    # Generic static extraction of HTML-valued JavaScript strings, including
    # CCTV's `var contentdate = '<p>...</p>'` payload.
    if source_override is None:
        for script in soup.find_all("script"):
            script_text = script.string or script.get_text()
            for match in _SCRIPT_ASSIGNMENT.finditer(script_text):
                quote = match.group(2)
                cursor = match.end()
                escaped = False
                end = None
                while cursor < len(script_text):
                    char = script_text[cursor]
                    if char == quote and not escaped:
                        end = cursor
                        break
                    escaped = char == "\\" and not escaped
                    if char != "\\":
                        escaped = False
                    cursor += 1
                if end is None:
                    continue
                decoded = _decode_static_script_string(script_text[match.end():end])
                if decoded.count("<p") + decoded.count("<h2") + decoded.count("<figure") < 2:
                    continue
                candidate = _candidate_from_html(f"text-{index:03d}", "script_html", match.group(1), decoded, title, index)
                if candidate:
                    candidates.append(candidate)
                    index += 1
    for meta_name in ("description", "og:description"):
        for node in soup.select(f'meta[name="{meta_name}"], meta[property="{meta_name}"]'):
            value = node.get("content", "")
            candidate = _candidate_from_html(f"text-{index:03d}", "metadata", meta_name, f"<p>{html_escape.escape(value)}</p>", title, index)
            if candidate:
                candidates.append(candidate)
                index += 1
    return candidates


def _deduplicate_text_candidates(candidates: list[ArticleTextCandidate]) -> list[ArticleTextCandidate]:
    result: list[ArticleTextCandidate] = []
    groups: list[tuple[str, str]] = []
    for candidate in candidates:
        normalized = candidate.text.lower()
        duplicate_group = None
        for group_id, existing in groups:
            ratio = SequenceMatcher(None, normalized[:12000], existing[:12000]).ratio()
            if ratio >= .86 or (len(normalized) > 500 and (normalized in existing or existing in normalized)):
                duplicate_group = group_id
                break
        if duplicate_group is None:
            duplicate_group = f"text-group-{len(groups):03d}"
            groups.append((duplicate_group, normalized))
        result.append(candidate.model_copy(update={"duplicate_group": duplicate_group}))
    return result


def _candidate_score(candidate: ArticleTextCandidate) -> float:
    score = min(candidate.char_count / 2000, 8.0) + candidate.paragraph_count * 1.5 + candidate.image_count * 2
    if candidate.source in {"dom", "script_html", "rendered_dom"}:
        score += 8
    if candidate.source in _METADATA_SOURCES:
        score -= 12
    if candidate.paragraph_count < 2:
        score -= 8
    parsed = BeautifulSoup(candidate.html, "html.parser")
    link_text = sum(len(_normalize_text(link.get_text(" ", strip=True))) for link in parsed.find_all("a"))
    if candidate.char_count and link_text / candidate.char_count > .35:
        score -= 15
    ui_hits = 0
    for node in parsed.find_all(True):
        _, hits = _article_ui_match(node)
        ui_hits += len(hits)
    if ui_hits:
        score -= min(18.0, ui_hits * 2.5)
    if candidate.paragraph_count and candidate.char_count / candidate.paragraph_count < 24:
        score -= 4
    return score


def _preview(candidate: ArticleTextCandidate) -> CandidatePreview:
    text = candidate.text
    midpoint = len(text) // 2
    return CandidatePreview(id=candidate.id, source=candidate.source, selector_or_key=candidate.selector_or_key, char_count=candidate.char_count, paragraph_count=candidate.paragraph_count, image_count=candidate.image_count, title_context=candidate.title_context, beginning=text[:360], middle=text[max(0, midpoint - 180):midpoint + 180], ending=text[-360:])


def classify_content_sufficiency(body: str, *, representation: str = "text") -> tuple[str, dict]:
    """Classify grounded article content without guessing its representation.

    Plain article text commonly contains command placeholders such as
    ``<path>``. Treating every angle bracket as HTML discards that content and
    makes an otherwise valid article fail extraction.
    """
    if representation not in {"text", "html"}:
        raise ValueError("representation must be 'text' or 'html'")
    parsed = BeautifulSoup(body, "html.parser") if representation == "html" else None
    text = _normalize_text(parsed.get_text(" ", strip=True)) if parsed else _normalize_text(body)
    paragraphs = ([node for node in parsed.find_all(["p", "h2", "h3", "li"]) if _normalize_text(node.get_text(" ", strip=True))] if parsed else [line for line in body.splitlines() if _normalize_text(line)])
    paragraph_texts = [_normalize_text(node.get_text(" ", strip=True) if hasattr(node, "get_text") else str(node)) for node in paragraphs]
    substantive = [item for item in paragraph_texts if len(item) >= 24]
    text_density = len(text) / max(len(body), 1)
    links = sum(len(_normalize_text(node.get_text(" ", strip=True))) for node in parsed.find_all("a")) if parsed else 0
    link_ratio = links / max(len(text), 1)
    duplicate_ratio = 1 - len(set(paragraph_texts)) / max(len(paragraph_texts), 1)
    valid_length = len(text) >= 80 and len(paragraphs) >= 2
    # A short, single-paragraph article is still usable when it contains a
    # substantive continuous passage. Metadata candidates are filtered by the
    # caller and cannot reach this exception as a replacement for article body.
    if len(paragraphs) == 1 and len(text) >= 120 and substantive:
        valid_length = True
    valid = valid_length and text_density >= .08 and link_ratio <= .35 and duplicate_ratio < .35
    classification = "invalid" if not valid else ("compact" if len(text) < 600 or len(substantive) < 3 else "normal")
    return classification, {
        "classification": classification,
        "char_count": len(text),
        "paragraph_count": len(paragraphs),
        "substantive_paragraph_count": len(substantive),
        "text_density": round(text_density, 4),
        "link_ratio": round(link_ratio, 4),
        "duplicate_ratio": round(duplicate_ratio, 4),
    }


def _quality_ok(body: str, *, representation: str = "text") -> bool:
    return classify_content_sufficiency(body, representation=representation)[0] != "invalid"


def _merge_text_candidates(candidates: list[ArticleTextCandidate], selected_ids: list[str]) -> ArticleExtractionResult:
    by_id = {candidate.id: candidate for candidate in candidates}
    selected = [by_id[item] for item in selected_ids if item in by_id]
    selected.sort(key=lambda item: (item.section_index, item.id))
    chosen_groups: set[str] = set()
    merged_paragraphs: list[str] = []
    selected_html: list[str] = []
    used_ids: list[str] = []
    for candidate in selected:
        if candidate.source in _METADATA_SOURCES and any(item.source not in _METADATA_SOURCES for item in selected):
            continue
        if candidate.duplicate_group and candidate.duplicate_group in chosen_groups:
            continue
        if candidate.duplicate_group:
            chosen_groups.add(candidate.duplicate_group)
        fragment = BeautifulSoup(candidate.html, "html.parser")
        for node in fragment.find_all(["p", "h2", "h3", "li"]):
            paragraph = _normalize_text(node.get_text(" ", strip=True))
            if paragraph and not any(SequenceMatcher(None, paragraph, existing).ratio() >= .92 for existing in merged_paragraphs):
                merged_paragraphs.append(paragraph)
        selected_html.append(str(fragment))
        used_ids.append(candidate.id)
    body = "\n".join(merged_paragraphs)
    used_candidates = [by_id[item] for item in used_ids]
    method = "+".join(dict.fromkeys(item.source for item in used_candidates)) or "deterministic"
    confidence = min(1.0, max(0.0, max((_candidate_score(item) for item in selected), default=0) / 20))
    return ArticleExtractionResult(requested_url="", canonical_url="", effective_base_url="", extraction_method=method, extraction_confidence=confidence, selected_candidate_ids=used_ids, title=used_candidates[0].title_context if used_candidates else "未命名文章", body=body, selected_html="<article>" + "".join(selected_html) + "</article>")


def _select_article_candidates(candidates: list[ArticleTextCandidate], title: str, *, artifact_dir: str | Path | None = None, contract_name: str = "article_selection") -> tuple[ArticleExtractionResult, dict]:
    diagnostics = {"candidate_total": len(candidates), "agent_sent": len(candidates), "agent_mode": "deterministic_fallback", "selected_candidate_ids": [], "fallback": True}
    if not candidates:
        return ArticleExtractionResult(requested_url="", canonical_url="", effective_base_url="", extraction_method="none", title=title, body=""), diagnostics
    by_id = {candidate.id: candidate for candidate in candidates}
    ranked = sorted(candidates, key=lambda item: (-_candidate_score(item), item.section_index, item.id))
    selected_ids = []
    for candidate in ranked:
        selected_ids.append(candidate.id)
        if _quality_ok(_merge_text_candidates(candidates, selected_ids).body):
            break
    provider = get_agent_provider("article")
    if provider.model_name != "mock":
        previews = [_preview(item).model_dump(mode="json") for item in candidates]
        prompt = {"task": "从已发现的正文候选中选择完整文章正文。只能返回候选 ID，不要生成正文或 URL。metadata 只能作为摘要辅助，不能替代完整正文。", "title": title, "candidates": previews}
        def validate_selection(value: ArticleSelectionDecision):
            issues = []
            seen = set()
            for index, candidate_id in enumerate(value.selected_candidate_ids):
                if candidate_id not in by_id:
                    issues.append(issue(("selected_candidate_ids", index), "unknown_candidate_id", f"candidate ID {candidate_id!r} is not present in input"))
                elif candidate_id in seen:
                    issues.append(issue(("selected_candidate_ids", index), "duplicate_candidate_id", f"candidate ID {candidate_id!r} is duplicated"))
                seen.add(candidate_id)
            return issues
        try:
            decision = StructuredAgentRunner().run(
                provider=provider, contract_name=contract_name, prompt=prompt,
                schema=ArticleSelectionDecision, artifact_dir=_agent_artifact_root(artifact_dir),
                semantic_validator=validate_selection,
            )
            selected_ids = decision.selected_candidate_ids
            validation_path = _agent_artifact_root(artifact_dir) / "agent_runs" / contract_name / "validation.json"
            repaired = validation_path.is_file() and json.loads(validation_path.read_text(encoding="utf-8"))["status"] == "passed_after_repair"
            diagnostics.update({"agent_mode": "retry_success" if repaired else "success", "fallback": False, "selected_candidate_ids": selected_ids, "confidence": decision.confidence, "reason": decision.reason})
        except Exception as exc:
            diagnostics.setdefault("agent_errors", []).append(f"{type(exc).__name__}: {exc}")
    result = _merge_text_candidates(candidates, selected_ids)
    result = result.model_copy(update={"title": title})
    diagnostics["selected_candidate_ids"] = result.selected_candidate_ids
    diagnostics["body_chars"] = len(result.body)
    diagnostics["method"] = result.extraction_method
    if not _quality_ok(result.body):
        # Deterministic fallback is complete and independent of model output.
        fallback_ids = []
        for candidate in ranked:
            if candidate.source in _METADATA_SOURCES and any(item.source not in _METADATA_SOURCES for item in ranked):
                continue
            fallback_ids.append(candidate.id)
            trial = _merge_text_candidates(candidates, fallback_ids)
            if _quality_ok(trial.body):
                result = trial.model_copy(update={"title": title})
                break
        diagnostics["fallback"] = True
        diagnostics["selected_candidate_ids"] = result.selected_candidate_ids
        diagnostics["body_chars"] = len(result.body)
        diagnostics["method"] = result.extraction_method
    return result, diagnostics


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


_SCREENSHOT_FONT_URL = "https://video-assistant.local/fonts/noto-sans-sc.ttf"


def capture_article_screenshots(source_url: str, project_dir: str | Path, start_index: int, count: int, diagnostics: dict | None = None, *, selected_html: str = "", body: str = "", title: str = "") -> list[ArticleImage]:
    """Capture distinct 16:9 regions from the already extracted article body.

    This function deliberately never navigates to ``source_url``. A page may
    allow the original HTTP fetch but reject Chromium with a 403, so screenshot
    fallback renders the trusted extraction result locally instead.
    """
    requested_count = count
    count = min(count, ARTICLE_SCREENSHOT_LIMIT)
    if diagnostics is not None:
        diagnostics.setdefault("screenshot_fallback", {}).update({
            "requested_count": requested_count,
            "allowed_count": max(0, count),
            "screenshot_limit": ARTICLE_SCREENSHOT_LIMIT,
        })
    if count <= 0:
        return []
    if not chromium_available():
        raise ValueError("正文截图引擎尚未安装；请运行 make browser")
    document, source, document_stats = _build_screenshot_document(selected_html, body, title)
    if document_stats["cleaned_chars"] < 80:
        raise ValueError("正文截图内容不足，无法生成本地排版")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
            _route_screenshot_assets(page)
            page.set_content(document, wait_until="domcontentloaded")
            page.evaluate("""async () => { await document.fonts.ready; }""")
            main = page.locator("#video-assistant-article")
            box = main.bounding_box()
            if not box or box["width"] < 320 or box["height"] < 180:
                raise ValueError("本地正文排版区域尺寸不足")
            # Playwright rejects a clip ending on a fractional document edge.
            # Use the floor of the rendered box, not scrollHeight's rounded-up
            # integer, so `y + height` is always inside the screenshot surface.
            page_size = page.evaluate("""() => {
                const root = document.documentElement.getBoundingClientRect();
                const body = document.body.getBoundingClientRect();
                return {
                    scrollWidth: Math.floor(Math.min(document.documentElement.scrollWidth, document.body.scrollWidth, root.width, body.width)),
                    scrollHeight: Math.floor(Math.min(document.documentElement.scrollHeight, document.body.scrollHeight, root.height, body.height)),
                };
            }""")
            crop_width = min(box["width"], 1280, page_size["scrollWidth"], page_size["scrollHeight"] * 16 / 9)
            crop_height = crop_width * 9 / 16
            if crop_width < 320 or crop_height < 180:
                raise ValueError("正文截图裁切区域尺寸不足")
            left = min(max(0, box["x"] + max(0, (box["width"] - crop_width) / 2)), max(0, page_size["scrollWidth"] - crop_width))
            # Chromium treats an edge-aligned clip as out of bounds when layout
            # has fractional pixels, so retain one CSS pixel of headroom.
            max_top = max(0, page_size["scrollHeight"] - crop_height - 1)
            output = Path(project_dir) / "article_downloads"
            output.mkdir(parents=True, exist_ok=True)
            result: list[ArticleImage] = []
            hashes: list[int] = []
            anchors = _screenshot_anchors(main, box, crop_height, max_top, count)
            if diagnostics is not None:
                diagnostics.setdefault("screenshot_fallback", {}).update({
                    "source": source,
                    "network_navigation": False,
                    **document_stats,
                    "page_size": page_size,
                    "article_box": box,
                    "clips": [],
                    "items": [],
                })
            for top, paragraph_index in anchors:
                if len(result) >= count:
                    break
                target = output / f"screenshot-{len(result):03d}.jpg"
                desired_top = min(max(0, top), max_top)
                viewport_height = 720
                max_scroll = max(0, page_size["scrollHeight"] - viewport_height)
                scroll_top = min(max(0, desired_top - (viewport_height - crop_height) / 2), max_scroll)
                crop_top = min(max(0, desired_top - scroll_top), viewport_height - crop_height)
                clip = {"x": left, "y": scroll_top + crop_top, "width": crop_width, "height": crop_height}
                if clip["x"] + clip["width"] > page_size["scrollWidth"] or clip["y"] + clip["height"] > page_size["scrollHeight"]:
                    raise ValueError("正文截图裁切区域超出页面边界")
                # Chromium's page-level clip fails beyond the first viewport for
                # some `set_content()` documents. Scroll then crop the viewport
                # bitmap locally, which keeps every coordinate inside 1280x720.
                page.evaluate("top => window.scrollTo(0, top)", scroll_top)
                page.screenshot(path=str(target), type="jpeg", quality=88)
                _normalize_screenshot(target, crop=(left, crop_top, crop_width, crop_height))
                digest = hashlib.sha256(target.read_bytes()).hexdigest()
                perceptual = _perceptual_hash(target)
                item = {"paragraph_index": paragraph_index, "sha256": digest, "perceptual_hash": f"{perceptual:016x}", "clip": {**clip, "right": left + crop_width, "bottom": top + crop_height}}
                if any(_hamming_distance(perceptual, previous) <= 4 for previous in hashes):
                    target.unlink(missing_ok=True)
                    item["status"] = "duplicate"
                    if diagnostics is not None:
                        diagnostics["screenshot_fallback"]["clips"].append(item["clip"])
                        diagnostics["screenshot_fallback"]["items"].append(item)
                    continue
                hashes.append(perceptual)
                item["status"] = "saved"
                if diagnostics is not None:
                    diagnostics["screenshot_fallback"]["clips"].append(item["clip"])
                    diagnostics["screenshot_fallback"]["items"].append(item)
                result.append(ArticleImage(id=f"article-{start_index + len(result):03d}", source_url=f"screenshot://article/{start_index + len(result)}", local_path=str(target), width=SCREENSHOT_SIZE[0], height=SCREENSHOT_SIZE[1], source_index=start_index + len(result), alt="文章正文截图", caption="", context="正文截图", sha256=digest))
            browser.close()
            if len(result) < count:
                if diagnostics is not None:
                    diagnostics["screenshot_fallback"].update({
                        "generated_count": len(result),
                        "shortfall": max(0, requested_count - len(result)),
                        "reduction_reason": "duplicate_or_insufficient_article_regions",
                    })
                if not result:
                    raise ValueError(f"正文截图内容重复，尝试 {len(anchors)} 个段落位置后未生成可用截图")
            elif diagnostics is not None:
                diagnostics["screenshot_fallback"].update({
                    "generated_count": len(result),
                    "shortfall": max(0, requested_count - len(result)),
                    **({"reduction_reason": "screenshot_limit_reached"} if requested_count > count else {}),
                })
            return result
    except Exception as exc:
        raise ValueError(f"本地正文截图失败：{exc}") from exc


def chromium_available() -> bool:
    try:
        completed = subprocess.run([sys.executable, "-m", "playwright", "install", "--list"], check=False, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0 and "chromium-" in completed.stdout


def _route_screenshot_assets(page) -> None:
    font_path = Path(__file__).resolve().parents[1] / "runtime" / "fonts" / "noto-sans-sc" / "NotoSansSC[wght].ttf"

    def route(route) -> None:
        if route.request.url == _SCREENSHOT_FONT_URL and font_path.is_file():
            route.fulfill(path=str(font_path), content_type="font/ttf")
        else:
            route.abort()

    page.route("**/*", route)


def _build_screenshot_document(selected_html: str, body: str, title: str) -> tuple[str, str, dict]:
    """Build an inert local document from an extraction result, never page DOM."""
    source = "selected_html" if selected_html.strip() else "extracted_body"
    raw = selected_html if selected_html.strip() else "".join(f"<p>{html_escape.escape(part)}</p>" for part in _body_paragraphs(body))
    soup = BeautifulSoup(raw, "html.parser")
    raw_chars = len(soup.get_text(" ", strip=True))
    cleaned_fragment, clean_stats = _clean_article_fragment(str(soup), strip_network_attrs=True)
    soup = cleaned_fragment
    for node in soup.select("link, style, svg, img, picture, source, video, audio, form, input, button, select, textarea"):
        node.decompose()
    candidates = soup.select("article, main, [role=main]")
    fragment = max(candidates, key=lambda node: len(node.get_text(" ", strip=True))) if candidates else (soup.body or soup)
    content = str(fragment)
    cleaned_text = fragment.get_text(" ", strip=True)
    paragraph_count = len(fragment.find_all(["p", "li", "blockquote", "pre", "h2", "h3"]))
    safe_title = html_escape.escape(title.strip())
    document = f"""<!doctype html><html><head><meta charset=\"utf-8\"><style>
      @font-face{{font-family:'Video Assistant Noto';src:url('{_SCREENSHOT_FONT_URL}') format('truetype');font-weight:100 900;font-display:block}}
      *{{box-sizing:border-box}} html,body{{margin:0;min-height:720px;background:#fff;color:#171717}}
      body{{font:28px/1.65 'Video Assistant Noto',sans-serif}} #video-assistant-article{{width:1120px;min-height:720px;margin:0 auto;padding:56px 72px}}
      h1{{font-size:42px;line-height:1.3;margin:0 0 38px}} h2,h3{{line-height:1.3;margin:34px 0 20px}} p,li,pre,blockquote{{margin:0 0 22px}}
      pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f4f4;padding:20px}} a{{color:inherit;text-decoration:none}}
    </style></head><body><article id=\"video-assistant-article\">{f'<h1>{safe_title}</h1>' if safe_title else ''}{content}</article></body></html>"""
    return document, source, {
        "raw_chars": raw_chars,
        "cleaned_chars": len(cleaned_text),
        "paragraph_count": paragraph_count,
        "cleaned_paragraph_count": paragraph_count,
        "ui_nodes_removed": clean_stats["ui_nodes_removed"],
        "structural_nodes_removed": clean_stats["structural_nodes_removed"],
        "ui_token_hits": clean_stats["ui_token_hits"],
    }


def _body_paragraphs(body: str) -> list[str]:
    return [part.strip() for part in re.split(r"\n{2,}|(?<=[。！？.!?])\s+(?=[^\s])", body) if part.strip()]


def _screenshot_anchors(main, box: dict, crop_height: float, max_top: float, count: int) -> list[tuple[float, int]]:
    paragraph_boxes: list[tuple[float, int]] = []
    locator = main.locator("p,li,blockquote,pre,h2,h3")
    for index in range(locator.count()):
        paragraph_box = locator.nth(index).bounding_box()
        if paragraph_box:
            # Keep a little context above a paragraph but do not pull an
            # unrelated table of contents or preceding platform fragment into
            # the screenshot window.
            paragraph_boxes.append((min(max(0, paragraph_box["y"] - 32), max_top), index))
    if not paragraph_boxes:
        paragraph_boxes = [(min(max(0, box["y"]), max_top), -1)]
    unique: list[tuple[float, int]] = []
    for anchor in paragraph_boxes:
        if not unique or abs(anchor[0] - unique[-1][0]) > 4:
            unique.append(anchor)
    primary_indices = sorted({round(index * (len(unique) - 1) / max(1, count - 1)) for index in range(min(count, len(unique)))})
    primary = [unique[index] for index in primary_indices]
    return primary + [anchor for anchor in unique if anchor not in primary]


def _clean_imported_article_document(imported_html: str, base_url: str) -> str:
    """Compatibility wrapper retained for callers that import browser HTML."""
    document, _, _ = _build_screenshot_document(imported_html, "", "")
    return document


def _normalize_screenshot(path: Path, crop: tuple[float, float, float, float] | None = None) -> None:
    with Image.open(path).convert("RGB") as image:
        if crop is not None:
            left, top, width, height = crop
            image = image.crop((round(left), round(top), round(left + width), round(top + height)))
        ImageOps.fit(image, SCREENSHOT_SIZE, Image.Resampling.LANCZOS, centering=(0.5, 0.5)).save(path, "JPEG", quality=90, optimize=True)


def _perceptual_hash(path: Path) -> int:
    with Image.open(path).convert("L").resize((8, 8), Image.Resampling.LANCZOS) as image:
        values = list(image.get_flattened_data()) if hasattr(image, "get_flattened_data") else list(image.getdata())
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

    def context_for(node, index: int) -> tuple[str, str, str, bool]:
        parent = node.find_parent(["figure", "article", "section", "p", "div"])
        nearby = parent.get_text(" ", strip=True)[:2000] if parent else ""
        figure = node.find_parent("figure")
        caption_node = figure.find("figcaption") if figure else None
        in_article = bool(node.find_parent(["article", "main"])) or bool(node.find_parent(class_=re.compile(r"(?:RichContent|RichText|article|post|entry|content)", re.I)))
        return str(node.get("alt", ""))[:600], (caption_node.get_text(" ", strip=True) if caption_node else "")[:1000], nearby, in_article

    def add(value: object, source_type: str, node, index: int, kind: AssetKind = AssetKind.image) -> None:
        if not value or str(value).startswith("data:"):
            return
        absolute = urljoin(brief.canonical_url, str(value))
        alt, caption, nearby, in_article = context_for(node, index)
        raw.append({"url": absolute, "source_type": source_type, "alt": alt, "caption": caption, "nearby": nearby, "in_article": in_article, "index": index, "kind": kind})

    for index, image in enumerate(soup.find_all("img")):
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
        # Keep every declared source. The high-quality `data-original` URL is
        # often present alongside a small `srcset` avatar or placeholder.
        for attribute, source_type in (("data-original", "data-original"), ("data-src", "data-src"), ("src", "src")):
            if image.get(attribute):
                counts["src"] += int(attribute == "src")
                add(image.get(attribute), source_type, image, index)

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
            if item["in_article"] and "article-content" not in merged[key].source_types:
                merged[key].source_types.append("article-content")
            continue
        suffix = Path(urlparse(item["url"]).path).suffix.lower()
        # Wikimedia raster thumbnails retain the original SVG name in their
        # path (for example ``...Diagram.svg/960px-Diagram.svg.png``). They
        # are PNG responses and must remain usable image candidates.
        is_svg = suffix == ".svg"
        if is_svg:
            counts["svg"] += 1
        source_types = [item["source_type"]]
        if item["in_article"]:
            source_types.append("article-content")
        merged[key] = AssetCandidate(id=f"asset-{len(merged):03d}", kind=item["kind"], source_url=item["url"], page_url=brief.effective_base_url or brief.url, section_index=item["index"], original_index=item["index"], source_types=source_types, alt=item["alt"], caption=item["caption"], nearby_text=item["nearby"], mime_type=mimetypes.guess_type(item["url"])[0] or "", is_svg=is_svg)
    diagnostics = {"asset_discovery": {**counts, "before_dedup": len(raw), "after_dedup": len(merged), "embedded_video": sum(item.kind == AssetKind.embedded_video for item in merged.values())}}
    return list(merged.values()), diagnostics


def basic_asset_filter(candidates: list[AssetCandidate], diagnostics: dict) -> list[AssetCandidate]:
    reasons = {"size": 0, "mime": 0, "icon_avatar_logo": 0, "qr_code": 0, "format": 0, "other": 0}
    rejected: list[dict] = []
    kept: list[AssetCandidate] = []
    for candidate in candidates:
        parsed = urlparse(candidate.source_url)
        reason = ""
        suffix = Path(parsed.path).suffix.lower()
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            reason = "other"
        elif candidate.kind == AssetKind.image and (
            _QR_TOKEN.search(f"{parsed.path} {parsed.query}")
            or _QR_TEXT_TOKEN.search(f"{candidate.alt} {candidate.caption}")
        ):
            reason = "qr_code"
        elif candidate.kind == AssetKind.image and _PARTNER_UI_TOKEN.search(f"{candidate.alt} {candidate.caption} {candidate.nearby_text}"):
            reason = "icon_avatar_logo"
        elif candidate.kind == AssetKind.image and (_UI_TOKEN.search(f"{parsed.path} {candidate.alt}") or _UI_SUBSTRING.search(f"{parsed.path} {candidate.alt} {candidate.caption}") or _UI_TEXT_TOKEN.search(f"{candidate.alt} {candidate.caption}")):
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


def _looks_like_qr_code(path: str | Path) -> bool:
    """Detect three stable QR finder patterns without an optional CV dependency."""
    with Image.open(path).convert("L") as source:
        source.thumbnail((600, 600), Image.Resampling.LANCZOS)
        width, height = source.size
        pixels = source.load()

        def runs(values: list[bool]) -> list[tuple[bool, int, int]]:
            output: list[tuple[bool, int, int]] = []
            start, current = 0, values[0]
            for index in range(1, len(values) + 1):
                value = values[index] if index < len(values) else not current
                if value != current:
                    output.append((current, start, index - start))
                    start, current = index, value
            return output

        def ratio(lengths: list[int]) -> bool:
            unit = sum(lengths) / 7
            return unit >= 1.2 and all(abs(lengths[index] - unit) <= unit * .8 for index in (0, 1, 3, 4)) and abs(lengths[2] - 3 * unit) <= 3 * unit * .45

        matches: list[tuple[int, int]] = []
        for y in range(height):
            horizontal = runs([pixels[x, y] < 128 for x in range(width)])
            for index in range(len(horizontal) - 4):
                pattern = horizontal[index:index + 5]
                lengths = [item[2] for item in pattern]
                if [item[0] for item in pattern] != [True, False, True, False, True] or not ratio(lengths):
                    continue
                x = round(pattern[0][1] + lengths[0] + lengths[1] + lengths[2] / 2)
                vertical = runs([pixels[x, row] < 128 for row in range(height)])
                if any([item[0] for item in part] == [True, False, True, False, True] and part[2][1] <= y < part[2][1] + part[2][2] and ratio([item[2] for item in part]) for part in (vertical[offset:offset + 5] for offset in range(len(vertical) - 4))):
                    matches.append((x, y))
        clusters: list[list[float]] = []
        for x, y in matches:
            for cluster in clusters:
                count = cluster[2]
                if abs(x - cluster[0] / count) < 20 and abs(y - cluster[1] / count) < 20:
                    cluster[0] += x
                    cluster[1] += y
                    cluster[2] += 1
                    break
            else:
                clusters.append([float(x), float(y), 1.0])
        minimum_cluster_size = max(8, min(width, height) * .025)
        return sum(cluster[2] >= minimum_cluster_size for cluster in clusters) >= 3


def prepare_candidate_thumbnails(candidates: list[AssetCandidate], project_dir: str | Path, diagnostics: dict, *, limit: int = CANDIDATE_THUMBNAIL_LIMIT) -> tuple[list[AssetCandidate], list[dict]]:
    ranked = sorted((item for item in candidates if item.kind == AssetKind.image and not item.is_svg), key=lambda item: (-_candidate_preference(item), item.original_index, item.id))[:limit]
    output = Path(project_dir) / "asset_thumbnails"
    output.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    headers = {"User-Agent": "Mozilla/5.0 (compatible; VideoAssistant/1.0)", "Accept": "image/avif,image/webp,image/*;q=0.8,*/*;q=0.1"}
    with httpx.Client(headers=headers, timeout=httpx.Timeout(20, connect=8), trust_env=True) as client:
        for index, candidate in enumerate(ranked):
            record = {"asset_id": candidate.id, "source_url": candidate.source_url, "status": "failed", "local_path": None}
            try:
                response = _download_with_retry(client, candidate.source_url, MAX_IMAGE_BYTES)
                if not response.headers.get("content-type", "").lower().startswith("image/"):
                    raise ValueError("mime_not_image")
                with Image.open(BytesIO(response.content)) as source:
                    source.seek(0)
                    image = ImageOps.exif_transpose(source).convert("RGB")
                    original_size = image.size
                    image.thumbnail((CANDIDATE_THUMBNAIL_EDGE, CANDIDATE_THUMBNAIL_EDGE), Image.Resampling.LANCZOS)
                    target = output / f"{index:03d}-{candidate.id}.jpg"
                    image.save(target, "JPEG", quality=75, optimize=True)
                record.update({"status": "ready", "local_path": str(target), "original_size": list(original_size), "thumbnail_size": list(image.size), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
            except (httpx.HTTPError, OSError, ValueError, Image.DecompressionBombError) as exc:
                record["error"] = f"{type(exc).__name__}: {exc}"
            records.append(record)
    diagnostics["candidate_thumbnails"] = {"limit": limit, "edge_px": CANDIDATE_THUMBNAIL_EDGE, "candidate_count": len(candidates), "shortlisted_count": len(ranked), "ready_count": sum(item["status"] == "ready" for item in records), "omitted_count": max(0, len(candidates) - len(ranked)), "items": records}
    return ranked, records


def _fallback_candidate_profile(candidate: AssetCandidate, thumbnail: dict | None = None) -> CandidateVisualProfile:
    metadata = f"{candidate.source_url} {candidate.alt} {candidate.caption} {candidate.nearby_text}"
    qr = bool(_QR_TOKEN.search(candidate.source_url) or _QR_TEXT_TOKEN.search(f"{candidate.alt} {candidate.caption}"))
    if thumbnail and thumbnail.get("status") == "ready" and thumbnail.get("local_path"):
        try:
            qr = qr or _looks_like_qr_code(thumbnail["local_path"])
        except (OSError, ValueError):
            pass
    partner = bool(_PARTNER_UI_TOKEN.search(metadata))
    page_ui = bool(_UI_TOKEN.search(metadata) or _UI_SUBSTRING.search(metadata) or _UI_TEXT_TOKEN.search(metadata))
    app_download = bool(re.search(r"(?:app\s*下载|下载客户端|ios\s*&\s*android)", metadata, re.I))
    role = ImageRole.data if _EDITORIAL_SIGNAL.search(metadata) else ImageRole.hero if "og:image" in candidate.source_types else ImageRole.evidence
    eligible = not (qr or partner or page_ui or app_download)
    return CandidateVisualProfile(asset_id=candidate.id, analysis_status="fallback", role=role if eligible else ImageRole.irrelevant, topics=candidate.alt.split()[:4], relevance=max(.05, min(.95, .25 + _candidate_preference(candidate) / 180)), visual_quality=.6, is_qr_code=qr, is_advertisement=partner, is_page_ui=page_ui, is_logo=page_ui, is_app_download=app_download, eligible=eligible, exclusion_reason="qr_code" if qr else "partner_or_advertisement" if partner else "page_ui_or_logo" if page_ui else "app_download" if app_download else "")


def analyze_candidate_thumbnails(brief: ArticleBrief, candidates: list[AssetCandidate], thumbnail_records: list[dict], diagnostics: dict, *, artifact_dir: str | Path | None = None) -> list[CandidateVisualProfile]:
    provider = get_agent_provider("asset")
    by_id = {item.id: item for item in candidates}
    thumbnails = {item["asset_id"]: item for item in thumbnail_records}
    ready_ids = [item.id for item in candidates if thumbnails.get(item.id, {}).get("status") == "ready"]
    resolved: dict[str, CandidateVisualProfile] = {}
    batches: list[dict] = []
    multimodal = getattr(provider, "complete_multimodal", None)

    def inspect(asset_ids: list[str], batch_index: int) -> set[str]:
        supplied = [by_id[asset_id] for asset_id in asset_ids]
        prompt = {"task": "按输入顺序分析每张候选缩略图。识别图片主题与文章相关性，并排除二维码、扫码推广、广告、合作伙伴卡片、页面 UI、logo 和 App 下载素材。正文中的数据表、趋势图、统计图、产品对比表、架构图和证据截图都是有效素材，即使字号较小也不得标记为无可辨识内容。不要在本批次内选择最终图片。图片内主题大标题必须是清晰完整的大字，logo、水印、按钮、代码和图表标签不算。", "article": {"title": brief.title, "summary": brief.summary, "topics": brief.topics}, "images_in_supplied_order": [{"asset_id": item.id, "alt": item.alt, "caption": item.caption, "context": item.nearby_text[:500], "source_types": item.source_types} for item in supplied], "allowed_roles": [role.value for role in ImageRole], "requirements": ["candidate_profiles 必须逐项完整覆盖所有输入 asset_id", "不得输出 analysis_status"]}
        expected = set(asset_ids)
        def validate_profiles(value: CandidateVisualAnalysisDecision):
            result = []
            seen = set()
            for index, profile in enumerate(value.candidate_profiles):
                if profile.asset_id not in expected:
                    result.append(issue(("candidate_profiles", index, "asset_id"), "unknown_asset_id", f"asset_id {profile.asset_id!r} is not present in this batch"))
                elif profile.asset_id in seen:
                    result.append(issue(("candidate_profiles", index, "asset_id"), "duplicate_asset_id", f"asset_id {profile.asset_id!r} is duplicated"))
                seen.add(profile.asset_id)
            for missing in sorted(expected - seen):
                result.append(issue(("candidate_profiles", f"missing-asset-id-{missing}"), "missing_asset_id", f"asset_id {missing!r} is missing"))
            return result
        decision = StructuredAgentRunner().run(
            provider=provider, contract_name=f"asset_visual_batch-{batch_index:03d}", prompt=prompt,
            schema=CandidateVisualAnalysisDecision, artifact_dir=_agent_artifact_root(artifact_dir),
            semantic_validator=validate_profiles,
            image_paths=[thumbnails[item.id]["local_path"] for item in supplied],
        )
        accepted: set[str] = set()
        for item in decision.candidate_profiles:
            profile = CandidateVisualProfile.model_validate(item.model_dump() | {"analysis_status": "verified"})
            blocked = profile.is_qr_code or profile.is_advertisement or profile.is_page_ui or profile.is_logo or profile.is_app_download
            if blocked:
                profile = profile.model_copy(update={"eligible": False, "role": ImageRole.irrelevant, "exclusion_reason": profile.exclusion_reason or "visual_non_editorial_asset"})
            elif not profile.eligible and "article-content" in by_id[profile.asset_id].source_types and not re.search(r"(?:与文章无关|不相关|unrelated|irrelevant)", profile.exclusion_reason, re.I):
                profile = profile.model_copy(update={"eligible": True, "role": ImageRole.evidence if profile.role == ImageRole.irrelevant else profile.role, "relevance": max(.3, profile.relevance), "exclusion_reason": f"vision_uncertain_preserved_for_global_ranking: {profile.exclusion_reason}"[:400]})
            resolved[profile.asset_id] = profile
            accepted.add(profile.asset_id)
        validation = json.loads((_agent_artifact_root(artifact_dir) / "agent_runs" / f"asset_visual_batch-{batch_index:03d}" / "validation.json").read_text(encoding="utf-8"))
        batches.append({"batch": batch_index, "attempts": len(validation["attempts"]), "asset_ids": asset_ids, "accepted_ids": sorted(accepted), "missing_ids": []})
        return accepted

    if provider.model_name != "mock" and callable(multimodal):
        for batch_index, start in enumerate(range(0, len(ready_ids), CANDIDATE_VISION_BATCH_SIZE), 1):
            batch_ids = ready_ids[start:start + CANDIDATE_VISION_BATCH_SIZE]
            try:
                inspect(batch_ids, batch_index)
            except Exception as exc:
                batches.append({"batch": batch_index, "asset_ids": batch_ids, "accepted_ids": [], "missing_ids": batch_ids, "error": f"{type(exc).__name__}: {exc}"})
    for candidate in candidates:
        resolved.setdefault(candidate.id, _fallback_candidate_profile(candidate, thumbnails.get(candidate.id)))
    profiles = [resolved[item.id] for item in candidates]
    diagnostics["candidate_visual_analysis"] = {"model": provider.model_name, "batch_size": CANDIDATE_VISION_BATCH_SIZE, "mode": "multimodal_with_fallback" if any(item.analysis_status == "verified" for item in profiles) else "deterministic_fallback", "verified_count": sum(item.analysis_status == "verified" for item in profiles), "fallback_count": sum(item.analysis_status != "verified" for item in profiles), "eligible_count": sum(item.eligible for item in profiles), "excluded_count": sum(not item.eligible for item in profiles), "batches": batches}
    return profiles


def _candidate_preference(item: AssetCandidate) -> float:
    """Deterministic editorial ranking when semantic selection is unavailable."""
    score = 0.0
    if item.kind == AssetKind.image:
        score += 100
    metadata = f"{item.source_url} {item.alt} {item.caption} {item.nearby_text}"
    if _QR_TOKEN.search(metadata) or _QR_TEXT_TOKEN.search(f"{item.alt} {item.caption}"):
        return -1000
    if "article-content" in item.source_types:
        score += 50
    if "data-original" in item.source_types:
        score += 45
    if item.caption:
        score += 20
    if item.nearby_text:
        score += 8
    if _EDITORIAL_SIGNAL.search(metadata):
        score += 28
    if _PARTNER_UI_TOKEN.search(metadata):
        score -= 70
    if "srcset" in item.source_types and "data-original" not in item.source_types:
        score -= 15
    if item.is_svg:
        score -= 8
    return score


def _ordered_candidate_pool(candidates: list[AssetCandidate], decisions: list[AssetDecision]) -> list[AssetCandidate]:
    by_id = {item.asset_id: item for item in decisions}
    return sorted(candidates, key=lambda candidate: (
        not by_id.get(candidate.id, AssetDecision(asset_id=candidate.id)).selected,
        -by_id.get(candidate.id, AssetDecision(asset_id=candidate.id)).relevance,
        -_candidate_preference(candidate),
        candidate.original_index,
        candidate.id,
    ))


def _local_asset_decisions(candidates: list[AssetCandidate], target_count: int = 3) -> list[AssetDecision]:
    ordered = sorted(candidates, key=lambda item: (-_candidate_preference(item), item.original_index, item.id))
    chosen = {item.id for item in ordered[:target_count]}
    first_id = ordered[0].id if ordered else ""
    return [AssetDecision(asset_id=item.id, selected=item.id in chosen, role=ImageRole.hero if item.id == first_id else ImageRole.evidence, topics=item.alt.split()[:4], relevance=max(.05, min(.95, .25 + _candidate_preference(item) / 180)) if item.kind == AssetKind.image else .05, visual_quality=.6, reason="deterministic candidate-pool fallback") for item in candidates]


def select_assets_with_agent(brief: ArticleBrief, candidates: list[AssetCandidate], diagnostics: dict, target_count: int = 3, *, visual_profiles: list[CandidateVisualProfile] | None = None, artifact_dir: str | Path | None = None) -> list[AssetDecision]:
    profile_by_id = {item.asset_id: item for item in visual_profiles or []}
    eligible_candidates = []
    for candidate in candidates:
        profile = profile_by_id.get(candidate.id)
        if profile is None:
            profile = _fallback_candidate_profile(candidate)
        if profile.eligible:
            eligible_candidates.append(candidate)
    if visual_profiles is not None:
        ranked_profiles = sorted((profile_by_id[item.id] for item in eligible_candidates), key=lambda item: (-item.title_match_score, -item.relevance, -item.visual_quality, item.asset_id))
        selected_ids = {item.asset_id for item in ranked_profiles[:target_count]}
        fallback = [AssetDecision(asset_id=item.id, selected=item.id in selected_ids, role=profile_by_id[item.id].role, topics=profile_by_id[item.id].topics, entities=profile_by_id[item.id].entities, relevance=profile_by_id[item.id].relevance, visual_quality=profile_by_id[item.id].visual_quality, title_match_score=profile_by_id[item.id].title_match_score, reason="candidate visual profile ranking") for item in eligible_candidates]
    else:
        fallback = _local_asset_decisions(eligible_candidates, target_count)
    diagnostics["asset_agent"] = {"sent": len(candidates), "mode": "local_fallback", "selected": 0, "decisions": [], "attempts": []}
    if not eligible_candidates:
        return fallback
    provider = get_agent_provider("asset")
    if provider.model_name == "mock":
        decisions = fallback
    else:
        prompt = {"task": "根据已经合并完成的候选视觉档案做一次全局排序，选择约 target_count 个互补素材。优先正文图表、数据图、流程/架构图、与标题匹配的大标题图、产品界面和关键证据。只能引用输入 asset_id，必须返回全部输入项。", "target_count": target_count, "article": {"title": brief.title, "text": brief.text[:9000]}, "assets": [{"candidate": item.model_dump(mode="json"), "visual_profile": profile_by_id[item.id].model_dump(mode="json") if item.id in profile_by_id else None} for item in eligible_candidates], "allowed_roles": [role.value for role in ImageRole]}
        decisions = fallback
        expected_ids = {item.id for item in eligible_candidates}
        def validate_decisions(value: AssetSelectionDecision):
            result = []
            seen = set()
            for index, item in enumerate(value.asset_decisions):
                if item.asset_id not in expected_ids:
                    result.append(issue(("asset_decisions", index, "asset_id"), "unknown_asset_id", f"asset_id {item.asset_id!r} is not present in input"))
                elif item.asset_id in seen:
                    result.append(issue(("asset_decisions", index, "asset_id"), "duplicate_asset_id", f"asset_id {item.asset_id!r} is duplicated"))
                seen.add(item.asset_id)
            for missing in sorted(expected_ids - seen):
                result.append(issue(("asset_decisions", f"missing-asset-id-{missing}"), "missing_asset_id", f"asset_id {missing!r} is missing"))
            selected_count = sum(item.selected for item in value.asset_decisions)
            required_count = min(target_count, len(eligible_candidates))
            if selected_count != required_count:
                result.append(issue(
                    ("selected_count",), "selected_count_mismatch",
                    f"exactly {required_count} assets must be selected, got {selected_count}",
                    related_paths=tuple(("asset_decisions", index, "selected") for index in range(len(value.asset_decisions))),
                ))
            return result
        try:
            response = StructuredAgentRunner().run(
                provider=provider, contract_name="asset_selection", prompt=prompt,
                schema=AssetSelectionDecision, artifact_dir=_agent_artifact_root(artifact_dir),
                semantic_validator=validate_decisions,
            )
            by_decision_id = {item.asset_id: item for item in response.asset_decisions}
            decisions = [AssetDecision.model_validate(by_decision_id[item.id].model_dump()) for item in eligible_candidates]
            validation = json.loads((_agent_artifact_root(artifact_dir) / "agent_runs" / "asset_selection" / "validation.json").read_text(encoding="utf-8"))
            diagnostics["asset_agent"]["mode"] = "text_retry_success" if validation["status"] == "passed_after_repair" else "text_success"
            diagnostics["asset_agent"]["attempts"] = validation["attempts"]
        except Exception as exc:
            validation_path = _agent_artifact_root(artifact_dir) / "agent_runs" / "asset_selection" / "validation.json"
            if validation_path.is_file():
                diagnostics["asset_agent"]["attempts"] = json.loads(validation_path.read_text(encoding="utf-8")).get("attempts", [])
            diagnostics["asset_agent"]["error"] = f"{type(exc).__name__}: {exc}"
        if decisions is fallback:
            diagnostics["asset_agent"].setdefault("error", "structured asset selection did not produce a valid decision")
    if sum(item.selected for item in decisions) < min(target_count, len(eligible_candidates)):
        ranked = sorted(decisions, key=lambda item: (-item.title_match_score, -item.relevance, -item.visual_quality, item.asset_id))
        selected_ids = {item.asset_id for item in ranked if item.selected}
        for item in ranked:
            if len(selected_ids) >= min(target_count, len(eligible_candidates)):
                break
            item.selected = True
            item.reason = item.reason or "deterministic target-count backfill"
            selected_ids.add(item.asset_id)
    elif sum(item.selected for item in decisions) > target_count:
        ranked_selected = sorted((item for item in decisions if item.selected), key=lambda item: (-item.title_match_score, -item.relevance, -item.visual_quality, item.asset_id))
        selected_ids = {item.asset_id for item in ranked_selected[:target_count]}
        for item in decisions:
            item.selected = item.asset_id in selected_ids
    globally_ranked = sorted(decisions, key=lambda item: (
        not item.selected,
        -item.title_match_score,
        -item.relevance,
        -item.visual_quality,
        item.asset_id,
    ))
    diagnostics["asset_agent"].update({
        "target_count": target_count,
        "eligible_count": len(eligible_candidates),
        "excluded_before_selection": len(candidates) - len(eligible_candidates),
        "selected": sum(item.selected for item in decisions),
        "global_ranked_asset_ids": [item.asset_id for item in globally_ranked],
        "decisions": [item.model_dump(mode="json") for item in decisions if item.selected],
    })
    return decisions


def image_tags_from_candidate_profiles(images: list[ArticleImage], candidates: list[AssetCandidate], profiles: list[CandidateVisualProfile]) -> list[ImageTag]:
    by_asset_id = {item.asset_id: item for item in profiles}
    candidate_by_url = {candidate.source_url: candidate for candidate in candidates}
    profile_by_url = {candidate.source_url: by_asset_id[candidate.id] for candidate in candidates if candidate.id in by_asset_id}
    tags: list[ImageTag] = []
    for image in images:
        profile = profile_by_url.get(image.source_url)
        if profile is None:
            tags.append(_fallback_tag(image))
            continue
        information_value = {
            ImageRole.data: .95, ImageRole.evidence: .85, ImageRole.diagram: .85,
            ImageRole.result: .85, ImageRole.product: .65, ImageRole.overview: .55,
            ImageRole.hero: .35, ImageRole.brand: .25,
        }.get(profile.role, .45)
        candidate = candidate_by_url.get(image.source_url)
        tags.append(ImageTag(image_id=image.id, candidate_profile_id=profile.asset_id, role=profile.role, topics=profile.topics, entities=profile.entities, salience=profile.relevance, visual_quality=profile.visual_quality, analysis_status=profile.analysis_status, is_logo=profile.is_logo, is_advertisement=profile.is_advertisement, is_page_ui=profile.is_page_ui, information_value=information_value, source_types=list(candidate.source_types) if candidate else [], section_index=image.source_index, contains_prominent_headline=profile.contains_prominent_headline, embedded_headline_text=profile.embedded_headline_text, headline_prominence=profile.headline_prominence, headline_title_match_score=profile.title_match_score, headline_bbox=profile.headline_bbox, headline_readability=profile.headline_readability, headline_analysis_status="verified" if profile.analysis_status == "verified" else "unavailable", headline_exclusion_reason=profile.exclusion_reason))
    return tags


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


def download_selected_assets(candidates: list[AssetCandidate], decisions: list[AssetDecision], project_dir: str | Path, diagnostics: dict, *, browser_imported: bool = False, max_renderable: int = 6) -> list[ArticleImage]:
    by_id = {candidate.id: candidate for candidate in candidates}
    candidate_pool = _ordered_candidate_pool(candidates, decisions)
    source_dir = Path(project_dir) / "materials" / "images"
    source_dir.mkdir(parents=True, exist_ok=True)
    stats = {"attempted": 0, "succeeded": 0, "failed": 0, "browser_asset_required": 0, "svg": 0, "jpeg": 0, "png": 0, "webp": 0, "other": 0, "items": [], "candidate_pool_total": len(candidate_pool), "selected_preference_count": sum(item.selected for item in decisions), "candidate_pool_exhausted": False, "renderable_count": 0}
    assets: list[ArticleImage] = []
    hashes: set[str] = set()
    perceptual_hashes: list[int] = []
    headers = {"User-Agent": "Mozilla/5.0 (compatible; VideoAssistant/1.0)", "Accept": "image/avif,image/webp,image/*,video/*;q=0.8,*/*;q=0.1"}
    with httpx.Client(headers=headers, timeout=httpx.Timeout(20, connect=8), trust_env=True) as client:
        for index, item in enumerate(candidate_pool):
            if len(assets) >= max_renderable:
                break
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
    stats["renderable_count"] = len(assets)
    stats["candidate_pool_exhausted"] = len(assets) < max_renderable and stats["attempted"] == len(candidate_pool)
    diagnostics["downloader"] = stats
    return assets


def log_asset_diagnostics(diagnostics: dict) -> None:
    for label, key in (("Article Extraction", "article_extraction"), ("Asset Discovery", "asset_discovery"), ("Rule Filter", "rule_filter"), ("Asset Agent", "asset_agent"), ("Downloader", "downloader"), ("Project Compile", "project_compile"), ("Screenshot Fallback", "screenshot_fallback")):
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


def _fallback_tag(image: ArticleImage, *, headline_status: str = "unavailable") -> ImageTag:
    text = f"{image.alt} {image.caption} {image.context}".lower()
    role = ImageRole.data if any(word in text for word in ("chart", "data", "数据", "图表")) else ImageRole.demo if any(word in text for word in ("demo", "界面", "截图", "screen")) else ImageRole.hero if image.source_index == 0 else ImageRole.evidence
    return ImageTag(image_id=image.id, role=role, topics=[word for word in image.alt.split()[:4]], salience=0.9 if role == ImageRole.hero else 0.6, visual_quality=min(1.0, image.width * image.height / 2_000_000), section_index=image.source_index, headline_analysis_status=headline_status, headline_exclusion_reason="image pixels were not analyzed" if headline_status == "unavailable" else "image headline analysis failed")


def _with_headline_status(tags: list[ImageTag], status: str) -> list[ImageTag]:
    if status == "verified":
        return [tag.model_copy(update={"headline_analysis_status": "verified"}) for tag in tags]
    return [tag.model_copy(update={
        "contains_prominent_headline": None,
        "embedded_headline_text": "",
        "headline_prominence": 0.0,
        "headline_title_match_score": 0.0,
        "headline_bbox": None,
        "headline_readability": 0.0,
        "headline_analysis_status": status,
        "headline_exclusion_reason": "image pixels were not analyzed" if status == "unavailable" else "image headline analysis failed",
    }) for tag in tags]


def analyze_prominent_headlines(brief: ArticleBrief, images: list[ArticleImage], tags: list[ImageTag], *, artifact_dir: str | Path | None = None) -> list[ImageTag]:
    """Inspect actual pixels in bounded batches without shrinking the image pool."""
    provider = get_agent_provider("asset")
    multimodal = getattr(provider, "complete_multimodal", None)
    if provider.model_name == "mock" or not callable(multimodal):
        return _with_headline_status(tags, "unavailable")
    if tags and all(tag.headline_analysis_status == "verified" for tag in tags):
        return tags
    by_id = {tag.image_id: tag for tag in tags}
    resolved: dict[str, ImageTag] = {}

    def inspect(batch: list[ArticleImage], batch_index: int) -> None:
        prompt = {
            "task": "按所列顺序检查实际图片像素，只判断图片中是否存在可作为视频开场的醒目主题大标题。正文截图允许入选，但普通正文段落、导航 UI、错误提示、logo、水印、按钮、代码和图表标签不算主题大标题。必须逐项返回且只能返回输入 image_id。embedded_headline_text 必须是图片中可见原文，bbox 为归一化 [x,y,width,height]。",
            "article_title": brief.title,
            "images_in_supplied_order": [{"image_id": image.id, "source_hint": "article_screenshot" if image.source_url.startswith("screenshot://") else "downloaded_image", "alt": image.alt, "caption": image.caption} for image in batch],
        }
        expected = {image.id for image in batch}
        def validate_headlines(value: ImageHeadlineBatchDecision):
            result = []
            seen = set()
            for index, item in enumerate(value.image_headlines):
                if item.image_id not in expected:
                    result.append(issue(("image_headlines", index, "image_id"), "unknown_image_id", f"image_id {item.image_id!r} is not present in this batch"))
                elif item.image_id in seen:
                    result.append(issue(("image_headlines", index, "image_id"), "duplicate_image_id", f"image_id {item.image_id!r} is duplicated"))
                seen.add(item.image_id)
            for missing in sorted(expected - seen):
                result.append(issue(("image_headlines", f"missing-image-id-{missing}"), "missing_image_id", f"image_id {missing!r} is missing"))
            return result
        decision = StructuredAgentRunner().run(
            provider=provider, contract_name=f"asset_headline_batch-{batch_index:03d}", prompt=prompt,
            schema=ImageHeadlineBatchDecision, artifact_dir=_agent_artifact_root(artifact_dir),
            semantic_validator=validate_headlines, image_paths=[image.local_path for image in batch],
        )
        for result in decision.image_headlines:
            image_id = result.image_id
            item = result.model_dump(mode="json")
            prominent = result.contains_prominent_headline
            if not prominent:
                item = item | {
                    "contains_prominent_headline": False,
                    "embedded_headline_text": "",
                    "headline_prominence": 0.0,
                    "headline_title_match_score": 0.0,
                    "headline_bbox": None,
                    "headline_readability": 0.0,
                }
            data = by_id[image_id].model_dump(mode="json") | item | {"headline_analysis_status": "verified"}
            resolved[image_id] = ImageTag.model_validate(data)

    for batch_index, start in enumerate(range(0, len(images), 4), 1):
        batch = images[start:start + 4]
        try:
            inspect(batch, batch_index)
        except Exception as batch_exc:
            for image in batch:
                base = by_id[image.id]
                resolved[image.id] = base.model_copy(update={
                    "contains_prominent_headline": None,
                    "embedded_headline_text": "",
                    "headline_prominence": 0.0,
                    "headline_title_match_score": 0.0,
                    "headline_bbox": None,
                    "headline_readability": 0.0,
                    "headline_analysis_status": "failed",
                    "headline_exclusion_reason": f"{type(batch_exc).__name__}: batch contract failed"[:300],
                })
    return [resolved.get(image.id, by_id[image.id]) for image in images]


def tag_images(brief: ArticleBrief, images: list[ArticleImage], *, artifact_dir: str | Path | None = None) -> tuple[ArticleBrief, VideoCopy, list[ImageTag]]:
    provider = get_agent_provider("asset")
    fallback_copy = VideoCopy(headline=brief.title[:80], subtitle=(brief.site_name or "文章要点")[:40], body=brief.text[:180])
    fallback_tags = [_fallback_tag(image) for image in images]
    if provider.model_name == "mock":
        return brief.model_copy(update={"summary": fallback_copy.body, "topics": fallback_tags[0].topics}), fallback_copy, fallback_tags
    payload = {"title": brief.title, "site": brief.site_name, "text": brief.text[:9000], "images": [{"id": image.id, "alt": image.alt, "caption": image.caption, "context": image.context[:800], "size": [image.width, image.height]} for image in images]}
    prompt = {"task": "阅读文章并分析每张实际图片。必须区分图片内部醒目的主题标题与 logo、水印、按钮、导航、代码、图表标签或零散 UI 文字。只有图片像素中确实存在清晰、完整、与文章标题相关的大字时，contains_prominent_headline 才能为 true。headline_bbox 使用归一化 [x,y,width,height]。", "article": payload}
    try:
        multimodal = getattr(provider, "complete_multimodal", None)
        expected = {image.id for image in images}
        def validate_tags(value: ArticleImageTaggingDecision):
            result = []
            seen = set()
            for index, tag in enumerate(value.image_tags):
                if tag.image_id not in expected:
                    result.append(issue(("image_tags", index, "image_id"), "unknown_image_id", f"image_id {tag.image_id!r} is not present in input"))
                elif tag.image_id in seen:
                    result.append(issue(("image_tags", index, "image_id"), "duplicate_image_id", f"image_id {tag.image_id!r} is duplicated"))
                seen.add(tag.image_id)
            for missing in sorted(expected - seen):
                result.append(issue(("image_tags", f"missing-image-id-{missing}"), "missing_image_id", f"image_id {missing!r} is missing"))
            return result
        result = StructuredAgentRunner().run(
            provider=provider, contract_name="article_image_tagging", prompt=prompt,
            schema=ArticleImageTaggingDecision, artifact_dir=_agent_artifact_root(artifact_dir),
            semantic_validator=validate_tags,
            image_paths=[image.local_path for image in images] if callable(multimodal) else None,
        )
        image_by_id = {image.id: image for image in images}
        tags = _with_headline_status([
            ImageTag.model_validate(item.model_dump() | {"section_index": image_by_id[item.image_id].source_index})
            for item in result.image_tags
        ], "verified" if callable(multimodal) else "unavailable")
        updated = brief.model_copy(update={"summary": result.summary, "topics": result.topics, "mood": result.mood})
        return updated, VideoCopy.model_validate(result.video_copy.model_dump()), analyze_prominent_headlines(brief, images, tags, artifact_dir=artifact_dir)
    except Exception:
        failed_tags = [_fallback_tag(image, headline_status="failed") for image in images]
        return brief.model_copy(update={"summary": fallback_copy.body, "topics": failed_tags[0].topics}), fallback_copy, analyze_prominent_headlines(brief, images, failed_tags, artifact_dir=artifact_dir)


def _title_match_score(title: str, image: ArticleImage, tag: ImageTag | None = None) -> float:
    haystack = f"{image.alt} {image.caption} {image.context} {' '.join(tag.topics if tag else [])} {' '.join(tag.entities if tag else [])}".lower()
    title = title.lower().strip()
    if not title or not haystack:
        return 0.0
    tokens = [token for token in re.split(r"[^\w\u4e00-\u9fff]+", title) if len(token) >= 2]
    matches = sum(token in haystack for token in tokens)
    metadata_score = min(1.0, matches / max(1, len(tokens)))
    trusted_visual_score = tag.headline_title_match_score if tag and tag.headline_analysis_status == "verified" and tag.role not in {ImageRole.brand, ImageRole.data, ImageRole.diagram, ImageRole.irrelevant} else 0.0
    return max(metadata_score, trusted_visual_score)


def _is_verified_title_card(image: ArticleImage, tag: ImageTag | None) -> bool:
    if not tag:
        return False
    if tag.role in {ImageRole.brand, ImageRole.data, ImageRole.diagram, ImageRole.irrelevant}:
        return False
    return bool(
        tag.headline_analysis_status == "verified"
        and tag.contains_prominent_headline
        and tag.embedded_headline_text.strip()
        and tag.headline_prominence >= .55
        and tag.headline_readability >= .6
        and tag.headline_title_match_score >= .45
    )


def _opening_image_score(title: str, image: ArticleImage, tag: ImageTag) -> dict:
    title_lower = title.lower()
    matched_entities = [entity for entity in tag.entities if len(entity.strip()) >= 2 and entity.lower() in title_lower]
    conflicting_entities = [entity for entity in tag.entities if len(entity.strip()) >= 2 and entity.lower() not in title_lower]
    entity_match = min(1.0, len(matched_entities) / max(1, min(2, len(tag.entities))))
    title_match = _title_match_score(title, image, tag)
    subject_match = max(title_match, entity_match)
    verified_title_card = _is_verified_title_card(image, tag)
    generic_ai_art = bool(re.search(r"(?:@ai_|ai[_-]?(?:img|image)|generated)", image.source_url, re.I)) and not verified_title_card
    subject_conflict = bool(tag.is_logo and conflicting_entities and not matched_entities)
    ineligible_reasons = []
    if tag.role == ImageRole.irrelevant or tag.is_advertisement or tag.is_page_ui:
        ineligible_reasons.append("non_editorial_asset")
    if subject_conflict:
        ineligible_reasons.append("core_entity_conflict")
    if generic_ai_art and tag.information_value < .5:
        ineligible_reasons.append("generic_decorative_image")
    confidence = 1.0 if tag.analysis_status == "verified" else .55 if tag.analysis_status == "fallback" else .35
    effective_salience = tag.salience * confidence
    source_bonus = .12 if "article-content" in tag.source_types else 0.0
    source_penalty = .22 if "og:image" in tag.source_types else 0.0
    role_bonus = {
        ImageRole.data: 1.0, ImageRole.evidence: .9, ImageRole.result: .9,
        ImageRole.diagram: .85, ImageRole.product: .65, ImageRole.overview: .55,
        ImageRole.hero: .35, ImageRole.brand: .2,
    }.get(tag.role, .4)
    score = (
        subject_match * .30
        + tag.information_value * .25
        + effective_salience * .20
        + tag.visual_quality * .15
        + role_bonus * .10
        + source_bonus
        - source_penalty
    )
    if generic_ai_art:
        score -= .25
    if verified_title_card:
        score += 1.0
    return {
        "eligible": not ineligible_reasons,
        "ineligible_reasons": ineligible_reasons,
        "score": round(score, 6),
        "verified_title_card": verified_title_card,
        "subject_match": round(subject_match, 6),
        "matched_entities": matched_entities,
        "conflicting_entities": conflicting_entities,
        "information_value": tag.information_value,
        "effective_salience": round(effective_salience, 6),
        "visual_quality": tag.visual_quality,
        "role_bonus": role_bonus,
        "analysis_status": tag.analysis_status,
        "generic_ai_art": generic_ai_art,
        "source_bonus": source_bonus,
        "source_penalty": source_penalty,
    }


def order_images(images: list[ArticleImage], tags: list[ImageTag], title: str = "", target_count: int | None = None, *, diagnostics: dict | None = None) -> tuple[list[ArticleImage], list[TransitionContext]]:
    by_id = {tag.image_id: tag for tag in tags}
    if not images:
        return [], []
    ranked = sorted(images, key=lambda image: (-by_id[image.id].salience, image.source_index))
    opening_scores = {image.id: _opening_image_score(title, image, by_id[image.id]) for image in images}
    eligible_openers = [image for image in images if opening_scores[image.id]["eligible"]]
    opener_pool = eligible_openers or images
    if not title.strip() and all(not by_id[item.id].source_types for item in images):
        # Compatibility for non-URL callers that never supplied article
        # context. URL projects always pass the localized title and use the
        # qualified opening score above.
        first = max(opener_pool, key=lambda image: (1 if by_id[image.id].role in {ImageRole.hero, ImageRole.overview} else 0, by_id[image.id].salience, -image.source_index))
    else:
        first = max(opener_pool, key=lambda image: (opening_scores[image.id]["score"], -image.source_index, image.id))
    if diagnostics is not None:
        diagnostics["opening_image_ranking"] = {
            "selected_image_id": first.id,
            "selection_reason": "highest_qualified_opening_score" if eligible_openers else "no_qualified_opener_fallback",
            "scores": [{"image_id": image.id, **opening_scores[image.id]} for image in sorted(images, key=lambda item: (-opening_scores[item.id]["score"], item.source_index))],
        }
    if target_count:
        remaining = [image for image in ranked if image.id != first.id][:max(0, target_count - 1)]
        ranked = [first, *remaining]
    last = min(ranked, key=lambda image: (0 if by_id[image.id].role in {ImageRole.result, ImageRole.brand, ImageRole.product} else 1, -by_id[image.id].salience, image.source_index))
    middle = sorted((image for image in ranked if image.id not in {first.id, last.id}), key=lambda image: image.source_index)
    ordered = [first, *middle]
    if last.id != first.id:
        ordered.append(last)
    contexts = [TransitionContext(from_image_id=current.id, to_image_id=nxt.id, relation=TransitionRelation.climax if index == len(ordered) - 2 else TransitionRelation.continuation, strength=0.9 if index == len(ordered) - 2 else 0.55) for index, (current, nxt) in enumerate(zip(ordered, ordered[1:]))]
    return ordered, contexts
