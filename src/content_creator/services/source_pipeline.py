"""Deterministic article and material tools used by the Source graph node."""
from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image, ImageOps

from content_creator.schemas import Material, SourceResult
from content_creator.services.article import (
    _brief_from_extraction,
    analyze_candidate_thumbnails,
    augment_soup_with_selected_html,
    basic_asset_filter,
    capture_article_screenshots,
    classify_content_sufficiency,
    discover_asset_candidates,
    download_selected_assets,
    extract_article_html,
    fetch_article_with_extraction,
    prepare_candidate_thumbnails,
    select_assets_with_agent,
)
from content_creator.services.article_localization import localize_article_copy
from content_creator.services.llm.router import require_agent_provider


def _write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def asset_target_count(character_count: int) -> int:
    return max(1, min(6, math.ceil(character_count / 1200)))


def _asset_preview_failure_details(analysis: dict, ready_ids: set[str], profile_by_id: dict) -> list[str]:
    details = [
        f"batch {batch['batch']}: {batch['error']}"
        for batch in analysis.get("batches", []) if batch.get("error")
    ]
    unverified_ids = sorted(
        asset_id for asset_id in ready_ids
        if asset_id not in profile_by_id or profile_by_id[asset_id].analysis_status != "verified"
    )
    if unverified_ids:
        details.append(f"unverified asset_ids: {', '.join(unverified_ids)}")
    return details


def _article_selection_succeeded(diagnostics: dict) -> bool:
    """Check the Article Agent's final state, not failed attempts it recovered from."""
    return (
        not diagnostics.get("fallback")
        and diagnostics.get("agent_mode") in {"success", "retry_success"}
    )


def _localize_materials(source_id: str, images, project_dir: Path) -> list[Material]:
    target_dir = project_dir / "materials"
    target_dir.mkdir(parents=True, exist_ok=True)
    materials: list[Material] = []
    for index, image in enumerate(images, start=1):
        source = Path(image.local_path).resolve()
        target = target_dir / f"{source_id}-{index:03d}.webp"
        with Image.open(source) as opened:
            normalized = ImageOps.exif_transpose(opened).convert("RGB")
            normalized.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
            normalized.save(target, "WEBP", quality=90, method=6)
            width, height = normalized.size
        materials.append(Material(
            id=f"{source_id}-material-{index:03d}", source_id=source_id,
            path=target.relative_to(project_dir).as_posix(), width=width, height=height,
            alt=image.alt, caption=image.caption,
        ))
    return materials


def process_source(
    *, source_id: str, url: str, project_dir: str | Path,
    imported_html: str | None = None, on_progress=None,
) -> SourceResult:
    """Run one mature article pipeline and persist a cacheable SourceResult."""
    project = Path(project_dir).resolve()
    source_dir = project / "sources" / source_id
    source_dir.mkdir(parents=True, exist_ok=True)
    cached = source_dir / "source_result.json"
    if cached.is_file():
        return SourceResult.model_validate_json(cached.read_text(encoding="utf-8"))

    def progress(message: str) -> None:
        if on_progress:
            on_progress(f"{source_id}：{message}")

    require_agent_provider("article")
    require_agent_provider("asset")
    progress("抓取并清洗文章")
    if imported_html is None:
        extraction, soup = fetch_article_with_extraction(url, agent_artifact_dir=source_dir)
    else:
        extraction, soup = extract_article_html(url, imported_html, agent_artifact_dir=source_dir)
    if not _article_selection_succeeded(extraction.diagnostics):
        raise RuntimeError(f"{source_id} Article Agent did not return a valid candidate selection")
    status, metrics = classify_content_sufficiency(extraction.body, representation="text")
    if status == "invalid":
        raise ValueError(f"{source_id} 没有可用于视频的有效正文")

    brief = _brief_from_extraction(extraction)
    brief, localized, localization = localize_article_copy(brief, artifact_dir=source_dir)
    soup = augment_soup_with_selected_html(soup, extraction.selected_html)
    target_count = asset_target_count(len(brief.text))
    diagnostics = {
        "source_id": source_id, "url": url, "content": metrics,
        "extraction": extraction.diagnostics, "localization": localization,
        "browser_imported": imported_html is not None,
    }

    progress("发现和筛选素材")
    candidates, discovery = discover_asset_candidates(soup, brief)
    diagnostics.update(discovery)
    filtered = basic_asset_filter(candidates, diagnostics)
    visual_candidates, previews = prepare_candidate_thumbnails(filtered, source_dir, diagnostics)
    profiles = analyze_candidate_thumbnails(brief, visual_candidates, previews, diagnostics, artifact_dir=source_dir)
    ready_ids = {item["asset_id"] for item in previews if item.get("status") == "ready"}
    profile_by_id = {profile.asset_id: profile for profile in profiles}
    analysis = diagnostics.get("candidate_visual_analysis", {})
    failure_details = _asset_preview_failure_details(analysis, ready_ids, profile_by_id)
    if failure_details:
        _write_json(source_dir / "diagnostics.json", diagnostics)
        raise RuntimeError(f"{source_id} Asset Agent preview analysis failed: {'; '.join(failure_details)}")
    decisions = select_assets_with_agent(brief, visual_candidates, diagnostics, target_count, visual_profiles=profiles, artifact_dir=source_dir)
    selection = diagnostics.get("asset_agent", {})
    if visual_candidates and selection.get("eligible_count", 0) and selection.get("mode") not in {"text_success", "text_retry_success"}:
        raise RuntimeError(f"{source_id} Asset Agent did not return a valid global ranking")
    if any("deterministic" in decision.reason for decision in decisions):
        raise RuntimeError(f"{source_id} Asset Agent ranking required an invalid deterministic repair")
    eligible = {profile.asset_id for profile in profiles if profile.eligible}
    images = download_selected_assets(
        [candidate for candidate in visual_candidates if candidate.id in eligible],
        decisions, source_dir, diagnostics,
        browser_imported=imported_html is not None, max_renderable=target_count,
    )
    if not images:
        progress("使用正文截图补充素材")
        images = capture_article_screenshots(
            brief.effective_base_url or brief.url, source_dir, 0, 1, diagnostics,
            selected_html=extraction.selected_html, body=extraction.body, title=extraction.title,
        )
    if not images:
        raise ValueError(f"{source_id} 没有可用视觉素材")
    materials = _localize_materials(source_id, images, project)
    result = SourceResult(
        source_id=source_id, url=url, title=localized.title, body="\n".join(localized.paragraphs),
        summary=localized.summary, materials=materials,
        metadata={
            "canonical_url": brief.canonical_url,
            "site_name": brief.site_name,
            "author": brief.author,
            "published_at": brief.published_at,
            "topics": brief.topics,
            "mood": brief.mood,
            "diagnostics_path": str(source_dir / "diagnostics.json"),
        },
    )
    _write_json(source_dir / "diagnostics.json", diagnostics)
    _write_json(cached, result)
    return result
