"""Deterministic copy-density intent and article-grounded narrative expansion."""
from __future__ import annotations

import re
from hashlib import sha256

from content_creator.schemas import ArticleBrief, CopyDensityIntent, NarrativeContent, SceneNarrative, VideoProject


INCREASE_TERMS = ("文案太少", "内容太少", "字太少", "太空", "空旷", "增加内容", "多一点", "上下都有", "more copy", "too little")
REDUCE_TERMS = ("文案太多", "内容太多", "字太多", "太挤", "精简", "减少内容", "少一点", "too much", "too dense")


def detect_copy_density_intent(reason: str) -> CopyDensityIntent:
    normalized = re.sub(r"\s+", "", reason).lower()
    if any(term.replace(" ", "") in normalized for term in INCREASE_TERMS):
        return CopyDensityIntent.increase
    if any(term.replace(" ", "") in normalized for term in REDUCE_TERMS):
        return CopyDensityIntent.reduce
    return CopyDensityIntent.preserve


def article_sentences(text: str) -> list[str]:
    boilerplate = ("当前文章被以下社区和专栏收录", "作者 |", "出品 |", "版权声明", "免责声明")
    ui_tokens = ("评论", "分享", "复制链接", "扫一扫", "举报", "收藏")
    parts = [re.sub(r"\s+", " ", part).strip() for part in re.split(r"(?<=[。！？!?])\s*|\n+", text)]
    return [part for part in parts if len(part) >= 12 and not any(token in part for token in boilerplate) and not any(token in part for token in ui_tokens)]


_PUNCT = r"[，、；：。！？,.!?;:]"


def _cut_with_ellipsis(text: str, index: int) -> str:
    """Cut at index, drop trailing Chinese punctuation/spaces, and mark the omission.

    English sentence punctuation is intentionally preserved so downstream
    language validation can still flag an English-only fragment.
    """
    return text[:index].rstrip(" ，、；：。！？") + "…"


def _prefix_at_boundary(text: str, target: int, hard_limit: int | None = None) -> str:
    if len(text) <= target:
        return text
    window = text[:target]
    # Prefer the last sentence punctuation inside the window.
    puncts = [match.end() for match in re.finditer(_PUNCT, window) if match.end() >= max(4, target // 2)]
    if puncts:
        return _cut_with_ellipsis(text, puncts[-1])
    # Otherwise fall back to the last space inside the window.
    spaces = [match.end() for match in re.finditer(r"\s+", window) if match.end() >= 3]
    if spaces:
        return _cut_with_ellipsis(text, spaces[-1])
    # No safe boundary in the window: extend past target to the next
    # punctuation/space instead of slicing a word in half.
    following = re.search(rf"{_PUNCT}|\s+", text[target:])
    if following and (hard_limit is None or target + following.end() < hard_limit):
        cut = target + following.end()
        if cut < len(text):
            return _cut_with_ellipsis(text, cut)
    cut = min(target, hard_limit - 1) if hard_limit is not None else target
    return _cut_with_ellipsis(text, cut)


def build_variants(text: str) -> tuple[str, str, str] | None:
    clean = re.sub(r"\s+", " ", text).strip()[:800]
    if len(clean) < 12:
        return None
    short_target = min(400, max(10, int(len(clean) * .7)))
    micro_target = min(180, max(8, int(len(clean) * .4)))
    short = _prefix_at_boundary(clean, short_target)
    micro = _prefix_at_boundary(clean, min(micro_target, len(short) - 1), hard_limit=len(short))
    if not (len(clean) > len(short) > len(micro) >= 4):
        short = _cut_with_ellipsis(clean, max(9, min(len(clean) - 1, short_target)))
        micro = _cut_with_ellipsis(clean, max(4, min(len(short) - 1, micro_target)))
    if not (len(clean) > len(short) > len(micro)):
        return None
    return clean, short, micro


def _content(text: str, *, content_id: str, segment_id: str, kind: str, source_index: int | None) -> NarrativeContent | None:
    variants = build_variants(text)
    if not variants:
        return None
    source_hash = sha256(re.sub(r"\s+", " ", text).strip().encode("utf-8")).hexdigest()
    unit = f"semantic-{sha256(f'{segment_id}:{kind}:{source_index}:{source_hash}'.encode()).hexdigest()[:12]}"
    return NarrativeContent(
        semantic_unit_id=unit,
        content_id=content_id,
        full=variants[0], short=variants[1], micro=variants[2],
        source_kind=kind, source_index=source_index, source_hash=source_hash,
    )


def expand_project_narratives(project: VideoProject, article: ArticleBrief, intent: CopyDensityIntent) -> tuple[dict[str, SceneNarrative], dict]:
    sentences = article_sentences(article.text)
    used_hashes: set[str] = set()
    expanded: dict[str, SceneNarrative] = {}
    source_cursor = 0
    before_chars = before_blocks = after_chars = after_blocks = 0

    for index, item in enumerate(project.timeline):
        if not item.narrative or not item.resolved_state:
            raise ValueError("copy density revision requires frozen narrative state")
        segment_id = item.resolved_state.segment_id
        original = item.narrative
        before_blocks += len(original.contents)
        before_chars += sum(len(content.value(block.variant_id)) for block in item.layout.text_blocks for content in original.contents if content.content_id == block.content_id) if item.layout else 0
        if intent == CopyDensityIntent.preserve:
            expanded[segment_id] = original.model_copy(update={"scene_id": segment_id})
            continue
        if intent == CopyDensityIntent.reduce:
            expanded[segment_id] = original.model_copy(update={"scene_id": segment_id, "contents": original.contents[:1]})
            continue

        sources: list[tuple[str, str, int | None]] = []
        if original.scene_purpose == "opening":
            sources.append((article.title, "title", None))
        elif original.scene_purpose == "conclusion" and sentences:
            sources.append((sentences[-1], "body", len(sentences) - 1))

        direction = range(len(sentences) - 1, -1, -1) if original.scene_purpose == "conclusion" else range(source_cursor, len(sentences))
        for sentence_index in direction:
            sentence = sentences[sentence_index]
            digest = sha256(sentence.encode("utf-8")).hexdigest()
            if digest in used_hashes or any(sentence == source[0] for source in sources):
                continue
            sources.append((sentence, "body", sentence_index))
            if original.scene_purpose != "conclusion":
                source_cursor = sentence_index + 1
            if len(sources) >= 2:
                break
        if len(sources) < 2 and article.summary:
            sources.append((article.summary, "summary", None))

        contents = []
        for source_index, (text, kind, paragraph_index) in enumerate(sources[:3]):
            content = _content(text, content_id="primary" if source_index == 0 else f"support-{source_index}", segment_id=segment_id, kind=kind, source_index=paragraph_index)
            if content and content.source_hash not in used_hashes:
                contents.append(content)
                used_hashes.add(content.source_hash)
        if len(contents) < 2:
            raise ValueError(f"没有更多可用正文：{segment_id} 无法构建第二个不重复字幕语义块")
        copy_id = f"copy-density-{sha256(f'{segment_id}:{contents[0].source_hash}'.encode()).hexdigest()[:12]}"
        expanded[segment_id] = original.model_copy(update={"copy_id": copy_id, "scene_id": segment_id, "contents": contents})

    for narrative in expanded.values():
        after_blocks += len(narrative.contents)
        after_chars += sum(len(content.short) for content in narrative.contents)
    return expanded, {
        "intent": intent.value,
        "before_character_count": before_chars,
        "after_candidate_character_count": after_chars,
        "before_block_count": before_blocks,
        "after_candidate_block_count": after_blocks,
    }
