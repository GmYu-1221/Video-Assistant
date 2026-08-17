"""Constrained adapter for the project-local Viral Writer skill."""
from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path

from content_creator.schemas import ArticleBrief, ImageTag, ViralCopyPlan, ViralCopyUnit, ViralTitleCandidate
from content_creator.services.article_localization import chinese_ratio, validate_localized_display_text
from content_creator.services.layout.copy_density import article_sentences, build_variants
from content_creator.services.llm.router import get_agent_provider
from content_creator.services.title_normalization import normalize_article_title


_SKILL_COMMIT = "1c76f891fb928ceb22fd101044d100d759f8cee5"
_FACT_TOKEN = re.compile(r"https?://\S+|(?<![\w.])\d+(?:\.\d+)*(?:%|万|亿|年|月|日|秒|分钟|小时)?")


def viral_writer_skill_path() -> Path:
    return Path(__file__).resolve().parents[3] / ".agents" / "skills" / "viral-writer" / "SKILL.md"


def load_viral_writer_skill() -> str:
    path = viral_writer_skill_path()
    if not path.is_file():
        raise RuntimeError("URL copy planning requires .agents/skills/viral-writer/SKILL.md")
    return path.read_text(encoding="utf-8")


def _clean_title(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" ，,。.!！?？:：")
    return value[:120]


def _fallback_titles(title: str) -> list[ViralTitleCandidate]:
    base = _clean_title(normalize_article_title(title)) or "文章核心内容"
    if not re.search(r"[\u3400-\u9fff]", base):
        base = f"{base} 项目介绍"
    if len(base) > 64:
        base = base[:64].rstrip(" ，,。.!！?？:：")
    options = [
        (base, "准确直述"),
        (f"一分钟看懂：{base}", "快速理解"),
        (f"{base}，关键是什么", "好奇心缺口"),
        (f"关于{base}，先看这几点", "信息前置"),
        (f"{base}到底值得关注什么", "问题钩子"),
    ]
    result: list[ViralTitleCandidate] = []
    seen: set[str] = set()
    for index, (text, strategy) in enumerate(options):
        text = _clean_title(text)
        if text in seen:
            text = _clean_title(f"{text}（{index + 1}）")
        seen.add(text)
        result.append(ViralTitleCandidate(
            candidate_id=f"title-{index + 1}", text=text, strategy=strategy,
            accuracy_score=max(.72, .96 - index * .05), clarity_score=max(.7, .94 - index * .04),
            attraction_score=min(.9, .62 + index * .07), image_match_score=.5,
        ))
    return result


def _fallback_plan(brief: ArticleBrief, target_count: int) -> ViralCopyPlan:
    source_hash = sha256(brief.text.encode("utf-8")).hexdigest()
    sources = article_sentences(brief.text)
    summary_only = not sources and bool(brief.summary)
    if summary_only:
        sources = [brief.summary]
    units: list[ViralCopyUnit] = []
    desired = min(24, max(1, target_count * 2))
    # Sample across the whole article. A fast reel should cover the opening,
    # representative evidence, and conclusion rather than narrating only the
    # first paragraphs when the model is unavailable.
    if len(sources) > desired:
        if desired == 1:
            selected_indices = [0]
        elif desired == 2:
            selected_indices = [0, len(sources) - 1]
        else:
            middle_count = desired - 2
            middle = [round(i * (len(sources) - 1) / (middle_count + 1)) for i in range(1, middle_count + 1)]
            selected_indices = [0, *middle, len(sources) - 1]
        selected_indices = list(dict.fromkeys(selected_indices))
    else:
        selected_indices = list(range(len(sources)))
    # If shortening a mixed Chinese/technical sentence creates an English-only
    # fragment, continue with another grounded sentence instead of letting the
    # bad micro variant fail much later during final render validation.
    priority_indices = [*selected_indices, *(index for index in range(len(sources)) if index not in selected_indices)]
    for source_index in priority_indices:
        source = sources[source_index]
        variants = build_variants(source)
        if variants is None or validate_localized_display_text(list(variants)):
            continue
        unit_index = len(units)
        purpose = "opening" if unit_index == 0 else "explanation" if unit_index % 2 else "evidence"
        normalized = re.sub(r"\s+", " ", source).strip()
        units.append(ViralCopyUnit(
            semantic_unit_id=f"viral-unit-{unit_index:03d}", content_id=f"viral-content-{unit_index:03d}",
            purpose=purpose, full=variants[0], short=variants[1], micro=variants[2],
            origin="source_rewrite", source_paragraph_indices=[] if summary_only else [source_index],
            source_hash=sha256(normalized.encode("utf-8")).hexdigest(),
        ))
        if len(units) >= desired:
            break
    if units:
        units[-1] = units[-1].model_copy(update={"purpose": "conclusion" if len(units) > 1 else "opening"})
    if not units:
        source = brief.summary or brief.text
        variants = build_variants(source)
        if variants is None:
            source = f"这篇文章介绍了{normalize_article_title(brief.title)}的核心内容与关键信息。"
            variants = build_variants(source)
        if variants is None:
            raise ValueError("Viral Writer fallback could not build readable copy")
        units = [ViralCopyUnit(
            semantic_unit_id="viral-unit-000", content_id="viral-content-000", purpose="opening",
            full=variants[0], short=variants[1], micro=variants[2], origin="source_rewrite",
            source_paragraph_indices=[], source_hash=source_hash,
        )]
    titles = _fallback_titles(brief.title)
    return ViralCopyPlan(
        source_article_hash=source_hash, title_candidates=titles,
        selected_title_id=titles[0].candidate_id, final_title=titles[0].text, content_units=units,
    )


def _strip_json(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I)
    return cleaned.strip()


def _validate_and_normalize(plan: ViralCopyPlan, brief: ArticleBrief, target_count: int) -> ViralCopyPlan:
    paragraphs = article_sentences(brief.text)
    source_article_hash = sha256(brief.text.encode("utf-8")).hexdigest()
    if plan.source_article_hash != source_article_hash:
        raise ValueError("viral copy plan source hash does not match the localized article")
    if validate_localized_display_text([item.text for item in plan.title_candidates]) or any(chinese_ratio(item.text) < .08 for item in plan.title_candidates):
        raise ValueError("Viral Writer returned an English explanatory title")
    if validate_localized_display_text([value for unit in plan.content_units for value in (unit.full, unit.short, unit.micro)]):
        raise ValueError("Viral Writer returned English explanatory copy")
    minimum_units = min(24, max(1, target_count * 2))
    if len(plan.content_units) < minimum_units:
        raise ValueError(f"Viral Writer returned too few semantic units: {len(plan.content_units)}/{minimum_units}")
    normalized_units: list[ViralCopyUnit] = []
    for unit in plan.content_units:
        if any(index >= len(paragraphs) for index in unit.source_paragraph_indices):
            raise ValueError("Viral Writer referenced an unknown source paragraph")
        referenced = " ".join(paragraphs[index] for index in unit.source_paragraph_indices)
        fact_tokens = _FACT_TOKEN.findall(unit.full)
        if fact_tokens and (not referenced or any(token not in referenced for token in fact_tokens)):
            raise ValueError("Viral Writer introduced an ungrounded factual token")
        digest_source = referenced or brief.text
        normalized_units.append(unit.model_copy(update={
            "source_hash": sha256(digest_source.encode("utf-8")).hexdigest(),
        }))
    ranked = sorted(plan.title_candidates, key=lambda item: item.ranking_score, reverse=True)
    selected = next((item for item in ranked if item.candidate_id == plan.selected_title_id), ranked[0])
    return plan.model_copy(update={
        "selected_title_id": selected.candidate_id,
        "final_title": selected.text,
        "content_units": normalized_units,
    })


def create_viral_copy_plan(brief: ArticleBrief, image_tags: list[ImageTag], target_count: int) -> tuple[ViralCopyPlan, dict]:
    fallback = _fallback_plan(brief, target_count)
    provider = get_agent_provider("article")
    diagnostics = {
        "model": provider.model_name,
        "skill_path": str(viral_writer_skill_path()),
        "skill_commit": _SKILL_COMMIT,
        "platform": "douyin_short_video",
    }
    if provider.model_name == "mock":
        return fallback, diagnostics | {"mode": "deterministic_fallback"}
    paragraphs = article_sentences(brief.text)
    prompt = json.dumps({
        "task": "使用 Viral Writer 的 11 个洞见维度，为 URL 竖屏短视频生成简体中文标题候选和冻结正文语义单元。只返回符合 schema 的 JSON。不要提问、保存 Markdown、生成配图建议或执行文件操作。采用快节奏剪辑：只保留核心观点、关键证据和结论，删除重复观点和次要章节，覆盖文章首尾及有代表性的中段，不要为了数量复制素材或文案。允许金句、类比、情绪和互动钩子；禁止虚构数字、人物、产品能力、案例或外部事实。普通英文说明必须翻译成中文，技术名、代码、命令和 URL 可保留。full/short/micro 必须是同一语义且长度严格递减，优先让 short/micro 在约 3.5 秒内可读。包含数字、URL 或可验证事实的单元必须列出支持它的 source_paragraph_indices。",
        "platform": "抖音短视频", "target_audience": "根据主题推断", "target_segment_count": target_count,
        "article": {"title": brief.title, "summary": brief.summary, "topics": brief.topics, "mood": brief.mood, "paragraphs": [{"source_index": index, "text": text} for index, text in enumerate(paragraphs)]},
        "image_semantics": [{"image_id": tag.image_id, "role": tag.role.value, "topics": tag.topics, "entities": tag.entities, "headline_text": tag.embedded_headline_text, "headline_title_match_score": tag.headline_title_match_score} for tag in image_tags],
        "requirements": {"title_candidates": 5, "content_units_min": min(24, max(1, target_count * 2)), "content_units_max": min(24, max(2, target_count * 2)), "source_article_hash": fallback.source_article_hash},
        "output_schema": ViralCopyPlan.model_json_schema(),
        "viral_writer_skill": load_viral_writer_skill(),
    }, ensure_ascii=False)
    try:
        candidate = ViralCopyPlan.model_validate(json.loads(_strip_json(provider.complete_json(prompt))))
        candidate = _validate_and_normalize(candidate, brief, target_count)
        return candidate, diagnostics | {"mode": "model_success"}
    except Exception as exc:
        return fallback, diagnostics | {"mode": "deterministic_fallback", "error": f"{type(exc).__name__}: {exc}"}


def ordered_title_texts(plan: ViralCopyPlan) -> list[str]:
    selected = plan.selected_title
    rest = sorted(
        (item for item in plan.title_candidates if item.candidate_id != selected.candidate_id),
        key=lambda item: item.ranking_score,
        reverse=True,
    )
    return [selected.text, *(item.text for item in rest)]
