"""Translate URL-pipeline display copy to simplified Chinese without inventing facts."""
from __future__ import annotations

import json
import re

from content_creator.schemas import ArticleBrief, LocalizedArticleCopy, VideoCopy
from content_creator.services.llm.router import get_agent_provider
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


def _parse_json(raw: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.I).strip()
    value = json.loads(cleaned)
    if not isinstance(value, dict):
        raise ValueError("translation_response_not_object")
    return value


def _translate_batch(provider, paragraphs: list[str], start: int, title: str, summary: str) -> tuple[dict[int, str], dict]:
    entries = [{"source_index": start + offset, "text": text} for offset, text in enumerate(paragraphs)]
    errors: list[str] = []
    pending_entries = entries
    first_title = ""
    first_summary = ""
    combined: dict[int, str] = {}
    for attempt in range(2):
        try:
            prompt = json.dumps({
                "task": "把输入文章段落逐条翻译成简体中文。必须翻译普通英文解释，不得原样返回。产品名、人名、技术名、代码、命令、文件名、URL 和 GitHub 路径保留原文。不得新增或删除事实。",
                "title": title if start == 0 and attempt == 0 else "",
                "summary": summary if start == 0 and attempt == 0 else "",
                "paragraphs": pending_entries,
                "previous_failure": "只修正未中文化的段落；冒号后的英文说明也必须翻译，技术名和 URL 保持原文。" if attempt else "",
                "output": {"title": "仅首批返回中文标题", "summary": "仅首批返回中文摘要", "paragraphs": [{"source_index": pending_entries[0]["source_index"], "zh_text": "中文翻译"}]},
            }, ensure_ascii=False)
            retry_prompt = prompt + "\n上次批次有段落未翻译。逐条返回全部 source_index，只输出 JSON。"
            if attempt == 0:
                raw = provider.complete_json(prompt)
            else:
                complete = getattr(provider, "complete", None)
                raw = complete(retry_prompt) if callable(complete) else provider.complete_json(retry_prompt)
            data = _parse_json(raw)
            rows = data.get("paragraphs") or data.get("translations")
            if not isinstance(rows, list):
                raise ValueError("translation_paragraphs_missing")
            translated: dict[int, str] = {}
            for row in rows:
                if not isinstance(row, dict) or "source_index" not in row:
                    raise ValueError("translation_source_index_missing")
                index = int(row["source_index"])
                if index not in {item["source_index"] for item in entries}:
                    raise ValueError(f"translation_unknown_source_index:{index}")
                value = str(row.get("zh_text", row.get("text", ""))).strip()
                if not value:
                    raise ValueError(f"translation_empty_source_index:{index}")
                translated[index] = value
            expected = {item["source_index"] for item in pending_entries}
            if set(translated) != expected:
                raise ValueError("translation_incomplete_source_indices:" + ",".join(map(str, sorted(expected - set(translated)))))
            first_title = first_title or str(data.get("title", "")).strip()
            first_summary = first_summary or str(data.get("summary", "")).strip()
            bad_indices = [index for index, value in translated.items() if validate_localized_display_text([value])]
            if bad_indices and attempt == 0:
                combined.update({index: value for index, value in translated.items() if index not in bad_indices})
                pending_entries = [item for item in entries if item["source_index"] in bad_indices]
                continue
            if bad_indices:
                # A gateway can still copy a technical sentence when several
                # difficult entries are bundled together. Give each failed
                # paragraph one focused Agent request before failing the job.
                complete = getattr(provider, "complete", None)
                for index in bad_indices:
                    source = next(item["text"] for item in pending_entries if item["source_index"] == index)
                    single_prompt = json.dumps({
                        "task": "只翻译这一条普通英文说明为简体中文。技术名、代码和 URL 保留原文，不得原样返回英文句子。只返回 JSON。",
                        "source_index": index,
                        "text": source,
                        "output": {"source_index": index, "zh_text": "中文翻译"},
                    }, ensure_ascii=False)
                    try:
                        single_errors = []
                        single_responses = []
                        if callable(complete):
                            single_responses.append(complete(single_prompt))
                            single_responses.append(complete(single_prompt + "\n再次确认：输出必须包含中文解释，不要只保留技术名或 URL。"))
                        single_responses.append(provider.complete_json(single_prompt))
                        for raw_single in single_responses:
                            try:
                                row = _parse_json(raw_single)
                                value = str(row.get("zh_text", "")).strip()
                                if int(row.get("source_index", index)) != index or not value or validate_localized_display_text([value]):
                                    raise ValueError("single_translation_not_chinese")
                                combined[index] = value
                                break
                            except Exception as single_exc:
                                single_errors.append(str(single_exc))
                        if index not in combined:
                            raise ValueError("single_translation_not_chinese:" + "|".join(single_errors))
                    except Exception as exc:
                        errors.append(f"single_{index}:{type(exc).__name__}:{exc}")
                expected_all = [item["source_index"] for item in entries]
                if all(index in combined for index in expected_all):
                    meta = {"attempts": attempt + 1, "single_fallback": True, "source_indices": sorted(combined), "title": first_title, "summary": first_summary}
                    return combined, meta
                raise ValueError("translation_not_chinese_source_indices:" + ",".join(map(str, bad_indices)))
            combined.update(translated)
            meta = {"attempts": attempt + 1, "source_indices": sorted(combined), "title": first_title, "summary": first_summary}
            return combined, meta
        except Exception as exc:
            errors.append(f"attempt_{attempt + 1}:{type(exc).__name__}:{exc}")
    raise ValueError(f"translation_batch_failed:{start}-{start + len(paragraphs) - 1}:" + " | ".join(errors))


def localize_article_copy(brief: ArticleBrief) -> tuple[ArticleBrief, LocalizedArticleCopy, dict]:
    paragraphs = _paragraphs(brief.text)
    original = " ".join([brief.title, brief.summary, *paragraphs])
    if chinese_ratio(original) >= 0.18:
        title = normalize_article_title(brief.title)
        copy = LocalizedArticleCopy(title=title, summary=brief.summary, paragraphs=paragraphs, source_paragraph_indices=list(range(len(paragraphs))), translation_mode="passthrough", chinese_text_ratio=chinese_ratio(original))
        issues = validate_localized_display_text([copy.title, copy.summary, *copy.paragraphs])
        if issues:
            raise ValueError("中文文案翻译失败：" + "; ".join(issues))
        localized = brief.model_copy(update={"title": title, "text": "\n".join(paragraphs)})
        return localized, copy, {"mode": "passthrough", "chinese_text_ratio": copy.chinese_text_ratio, "source_paragraph_indices": copy.source_paragraph_indices, "title_normalized": title != brief.title}
    provider = get_agent_provider("article")
    translated_by_index: dict[int, str] = {}
    batches: list[dict] = []
    for start in range(0, len(paragraphs), 7):
        batch = paragraphs[start:start + 7]
        translated, meta = _translate_batch(provider, batch, start, brief.title, brief.summary)
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
