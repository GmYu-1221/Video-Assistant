"""Deterministic display-title cleanup for URL video projects."""
from __future__ import annotations

import re


_PLATFORM_PREFIX = re.compile(r"^(?:GitHub|GitLab|Gitee)\s*[-|·]\s*", re.I)
_PLATFORM_SUFFIX = re.compile(r"\s*(?:[-|·]\s*)?(?:GitHub|GitLab|Gitee)\s*$", re.I)
_CONTENT_PLATFORM_SUFFIX = re.compile(r"\s*(?:[-|·]\s*)?(?:36氪|虎嗅|知乎|少数派|掘金|博客园|CSDN)\s*$", re.I)
_REPOSITORY_TITLE = re.compile(
    r"^(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)\s*(?:[:：]\s*(?P<description>.*))?$"
)
_PRODUCT_TITLE = re.compile(r"^(?P<product>[A-Za-z0-9_.-]+)\s*[:：]\s*(?P<description>.+)$")
_EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002700-\U000027BF]")


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" \t\r\n-|·")


def _first_chinese_phrase(value: str, *, include_commas: bool = True) -> str:
    separators = r"[。！？!?；;\n]"
    pieces = re.split(separators, _EMOJI.sub("。", value))
    phrase = next((piece.strip(" ,，:：") for piece in pieces if re.search(r"[\u3400-\u9fff]", piece)), "")
    if phrase and not include_commas:
        phrase = re.split(r"[，,：:]", phrase, maxsplit=1)[0].strip()
    return _clean(phrase)


def article_title_candidates(title: str) -> list[str]:
    """Return longest-to-shortest semantic title candidates.

    Repository SEO titles commonly repeat the same description in Chinese and
    English. Keep the repository identity and the first complete Chinese
    phrase instead of carrying the full page metadata into the video.
    """
    clean = _CONTENT_PLATFORM_SUFFIX.sub("", _PLATFORM_SUFFIX.sub("", _PLATFORM_PREFIX.sub("", _clean(title))))
    if not clean:
        return []

    candidates: list[str] = []
    repository = _REPOSITORY_TITLE.match(clean)
    if repository:
        repo = repository.group("repo")
        description = repository.group("description") or ""
        phrase = _first_chinese_phrase(description)
        short_phrase = _first_chinese_phrase(description, include_commas=False)
        if phrase:
            candidates.append(f"{repo}：{phrase}")
        if short_phrase and short_phrase != phrase:
            candidates.append(f"{repo}：{short_phrase}")
        candidates.append(f"{repo} 项目介绍")
    elif product := _PRODUCT_TITLE.match(clean):
        product_name = product.group("product")
        description = product.group("description")
        phrase = _first_chinese_phrase(description)
        short_phrase = _first_chinese_phrase(description, include_commas=False)
        if phrase:
            candidates.append(f"{product_name}：{phrase}")
        if short_phrase and short_phrase != phrase:
            candidates.append(f"{product_name}：{short_phrase}")
        candidates.append(f"{product_name} 项目介绍")
    else:
        candidates.append(clean)
        sentence = _first_chinese_phrase(clean)
        clause = _first_chinese_phrase(clean, include_commas=False)
        if sentence:
            candidates.append(sentence)
        if clause:
            candidates.append(clause)

    result: list[str] = []
    for candidate in candidates:
        candidate = _clean(candidate)
        if len(candidate) > 500:
            boundaries = [match.end() for match in re.finditer(r"[。！？!?；;，,：:]|\s+", candidate[:500])]
            if not boundaries:
                continue
            candidate = candidate[:boundaries[-1]].strip(" ,，:：;；")
        if candidate and candidate not in result:
            result.append(candidate)
    return result


def normalize_article_title(title: str) -> str:
    candidates = article_title_candidates(title)
    return candidates[0] if candidates else _clean(title)
