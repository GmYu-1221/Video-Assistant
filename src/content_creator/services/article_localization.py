"""Translate URL-pipeline display copy to simplified Chinese without inventing facts."""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from content_creator.schemas import ArticleBrief, ArticleTranslationBatchDecision, LocalizedArticleCopy, VideoCopy
from content_creator.services.llm.router import get_agent_provider
from content_creator.services.structured_agent import StructuredAgentRunner, issue
from content_creator.services.title_normalization import normalize_article_title


def chinese_ratio(value: str) -> float:
    chars = [char for char in value if not char.isspace()]
    return sum("\u4e00" <= char <= "\u9fff" for char in chars) / max(1, len(chars))


def _explanatory_english(value: str) -> bool:
    """Detect prose English while allowing short product/technology labels."""
    # Remove identifiers that are explicitly allowed to remain in English
    # before measuring the language of the explanatory sentence itself.
    comparable = re.sub(r"https?://\S+|\b[\w.-]+\.[A-Za-z]{2,}\b|\b(?=[A-Za-z0-9+_.-]*[A-Z0-9_-])[A-Za-z0-9+_.-]+\b", " ", value)
    words = re.findall(r"[A-Za-z]{2,}", comparable)
    if not words or chinese_ratio(comparable) >= 0.18:
        return False
    return len(words) >= 5 or bool(re.search(r"[.!?;:]", comparable))


def validate_localized_display_text(texts: list[str], *, minimum_ratio: float = 0.18) -> list[str]:
    issues: list[str] = []
    for index, text in enumerate(texts):
        normalized = re.sub(r"\s+", " ", text or "").strip()
        if normalized and _explanatory_english(normalized) and chinese_ratio(normalized) < minimum_ratio:
            issues.append(f"text-{index}: explanatory text is not Simplified Chinese")
    return issues


def build_localized_video_copy(brief: ArticleBrief, localized: LocalizedArticleCopy, preferred: VideoCopy | None = None) -> VideoCopy:
    """Keep the legacy copy fields synchronized with the URL narrative source."""
    title = localized.title.strip() or brief.title.strip()
    summary = localized.summary.strip() or (localized.paragraphs[0] if localized.paragraphs else brief.summary.strip())
    body = "\n".join(localized.paragraphs[:8]).strip() or brief.text.strip()
    # Preserve already-Chinese caller-authored copy for compatibility, while
    # rejecting English model output and always keeping the localized source.
    if preferred is not None:
        if preferred.headline and chinese_ratio(preferred.headline) >= 0.18:
            title = preferred.headline.strip()
        if preferred.subtitle and chinese_ratio(preferred.subtitle) >= 0.18:
            summary = preferred.subtitle.strip()
        if preferred.body and chinese_ratio(preferred.body) >= 0.18:
            body = preferred.body.strip()
    return VideoCopy(headline=title[:80], subtitle=summary[:40], body=body[:400])


def _paragraphs(text: str) -> list[str]:
    ui_exact = {
        "uh oh!", "code", "issues", "pull requests", "actions", "projects", "insights",
        "folders and files", "latest commit", "history", "repository files navigation",
        "table of contents", "about", "resources", "stars", "watchers", "forks",
        "releases", "packages", "used by", "contributors", "languages", "license",
    }
    ui_prefixes = ("notifications ", "fork ", "star ", "security and quality ", "issues ", "pull requests ")
    parts = [part.strip() for part in re.split(r"\n+|(?<=[!?。！？])\s+|(?<!\d)\.(?=\s+[A-Z\u4e00-\u9fff])", text)]
    result = []
    for part in parts:
        normalized = re.sub(r"\s+", " ", part).strip()
        lowered = normalized.lower()
        if len(normalized) < 8 or lowered in ui_exact or lowered.startswith(ui_prefixes):
            continue
        if lowered.startswith("there was an error while loading"):
            continue
        result.append(normalized)
    return result


def _translate_batch(provider, paragraphs: list[str], start: int, title: str, summary: str, *, artifact_dir: str | Path | None = None, batch_index: int = 1) -> tuple[dict[int, str], dict]:
    entries = [{"source_index": start + offset, "text": text} for offset, text in enumerate(paragraphs)]
    expected = {item["source_index"] for item in entries}
    prompt = {
        "task": "把输入文章段落逐条翻译成简体中文。必须翻译普通英文解释，不得原样返回。产品名、人名、技术名、代码、命令、文件名、URL 和 GitHub 路径保留原文。不得新增或删除事实。",
        "title": title if start == 0 else "", "summary": summary if start == 0 else "", "paragraphs": entries,
        "requirements": ["逐条且仅返回全部输入 source_index", "非首批的 title 和 summary 返回空字符串"],
    }
    def validate_translation(value: ArticleTranslationBatchDecision):
        result = []
        seen = set()
        for row_index, row in enumerate(value.paragraphs):
            if row.source_index not in expected:
                result.append(issue(("paragraphs", row_index, "source_index"), "unknown_source_index", f"source_index {row.source_index} is not present in this batch"))
            elif row.source_index in seen:
                result.append(issue(("paragraphs", row_index, "source_index"), "duplicate_source_index", f"source_index {row.source_index} is duplicated"))
            if validate_localized_display_text([row.zh_text]):
                result.append(issue(("paragraphs", row_index, "zh_text"), "translation_not_chinese", "ordinary explanatory prose must be translated to Simplified Chinese"))
            seen.add(row.source_index)
        for missing in sorted(expected - seen):
            result.append(issue(("paragraphs", f"missing-source-index-{missing}"), "missing_source_index", f"source_index {missing} is missing"))
        if start == 0:
            if not value.title or validate_localized_display_text([value.title]):
                result.append(issue(("title",), "translated_title_missing", "first batch must return a Simplified Chinese title"))
            if not value.summary or validate_localized_display_text([value.summary]):
                result.append(issue(("summary",), "translated_summary_missing", "first batch must return a Simplified Chinese summary"))
        else:
            if value.title:
                result.append(issue(("title",), "unexpected_batch_title", "non-first batch title must be empty"))
            if value.summary:
                result.append(issue(("summary",), "unexpected_batch_summary", "non-first batch summary must be empty"))
        return result
    root = Path(artifact_dir) if artifact_dir is not None else Path(tempfile.gettempdir()) / "video-assistant-agent-runs" / str(os.getpid())
    contract_name = f"article_translation_batch-{batch_index:03d}"
    decision = StructuredAgentRunner().run(
        provider=provider, contract_name=contract_name, prompt=prompt,
        schema=ArticleTranslationBatchDecision, artifact_dir=root,
        semantic_validator=validate_translation,
    )
    translated = {row.source_index: row.zh_text for row in decision.paragraphs}
    validation = json.loads((root / "agent_runs" / contract_name / "validation.json").read_text(encoding="utf-8"))
    return translated, {
        "attempts": len(validation["attempts"]), "source_indices": sorted(translated),
        "title": decision.title, "summary": decision.summary,
    }


def localize_article_copy(brief: ArticleBrief, *, artifact_dir: str | Path | None = None) -> tuple[ArticleBrief, LocalizedArticleCopy, dict]:
    paragraphs = _paragraphs(brief.text)
    original = " ".join([brief.title, brief.summary, *paragraphs])
    if chinese_ratio(original) >= 0.18:
        title = normalize_article_title(brief.title)
        header_issues = validate_localized_display_text([title, brief.summary])
        if header_issues:
            raise ValueError("中文文案翻译失败：" + "; ".join(header_issues))
        kept = [(index, paragraph) for index, paragraph in enumerate(paragraphs) if not validate_localized_display_text([paragraph])]
        excluded = [index for index, paragraph in enumerate(paragraphs) if validate_localized_display_text([paragraph])]
        if not kept:
            raise ValueError("中文文案翻译失败：没有可用的简体中文正文")
        kept_indices = [index for index, _ in kept]
        kept_paragraphs = [paragraph for _, paragraph in kept]
        ratio = chinese_ratio(" ".join([title, brief.summary, *kept_paragraphs]))
        copy = LocalizedArticleCopy(title=title, summary=brief.summary, paragraphs=kept_paragraphs, source_paragraph_indices=kept_indices, translation_mode="passthrough", chinese_text_ratio=ratio)
        localized = brief.model_copy(update={"title": title, "text": "\n".join(kept_paragraphs)})
        return localized, copy, {"mode": "passthrough", "chinese_text_ratio": copy.chinese_text_ratio, "source_paragraph_indices": copy.source_paragraph_indices, "excluded_non_chinese_paragraph_indices": excluded, "title_normalized": title != brief.title}
    provider = get_agent_provider("article")
    translated_by_index: dict[int, str] = {}
    batches: list[dict] = []
    for batch_index, start in enumerate(range(0, len(paragraphs), 7), 1):
        batch = paragraphs[start:start + 7]
        translated, meta = _translate_batch(provider, batch, start, brief.title, brief.summary, artifact_dir=artifact_dir, batch_index=batch_index)
        translated_by_index.update(translated)
        batches.append(meta)
    translated = [translated_by_index[index] for index in range(len(paragraphs))]
    title = brief.title
    summary = brief.summary
    if batches and batches[0].get("title"):
        title = batches[0]["title"]
    if batches and batches[0].get("summary"):
        summary = batches[0]["summary"]
    # Some compatible gateways omit optional title/summary fields even when
    # every indexed paragraph was translated. Keep the source title and use
    # the first translated paragraph as a deterministic summary.
    if not title:
        title = brief.title
    title = normalize_article_title(title)
    summary_parts = _paragraphs(summary) if summary else []
    if summary_parts:
        summary = " ".join(summary_parts[:2])
    else:
        summary = next((value for value in translated if len(value) >= 40), translated[0] if translated else brief.summary)
    if not title or not summary:
        raise ValueError("中文文案翻译失败：首批未返回标题或摘要")
    ratio = chinese_ratio(" ".join([title, summary, *translated]))
    issues = validate_localized_display_text([title, summary, *translated])
    if ratio < 0.18 or issues:
        raise ValueError("中文文案翻译失败：" + "; ".join(issues[:8] or ["translation_not_chinese"]))
    copy = LocalizedArticleCopy(title=title, summary=summary, paragraphs=translated, source_paragraph_indices=list(range(len(paragraphs))), translation_mode="model_batched", chinese_text_ratio=ratio)
    localized = brief.model_copy(update={"title": title, "summary": summary, "text": "\n".join(translated)})
    return localized, copy, {"mode": copy.translation_mode, "chinese_text_ratio": ratio, "source_paragraph_indices": copy.source_paragraph_indices, "batch_size": 7, "batches": batches, "batch_count": len(batches)}
