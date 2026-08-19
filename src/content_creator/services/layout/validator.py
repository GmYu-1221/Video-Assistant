from __future__ import annotations

from content_creator.schemas import ImageSemanticProfile, LayoutIssue, PersistentTitleSpec, Rect, SceneLayoutSpec, SceneNarrative, TypographyRole

SAFE = 60
MIN_FONT = {TypographyRole.display: 64, TypographyRole.headline: 48, TypographyRole.body: 32, TypographyRole.caption: 28, TypographyRole.metadata: 24, TypographyRole.quote: 40, TypographyRole.numeric: 56}
MAX_LINES = {TypographyRole.display: 3, TypographyRole.headline: 3, TypographyRole.body: 8, TypographyRole.caption: 3, TypographyRole.metadata: 2, TypographyRole.quote: 4, TypographyRole.numeric: 3}


def intersects(a, b) -> bool:
    return a.x < b.x + b.width and a.x + a.width > b.x and a.y < b.y + b.height and a.y + a.height > b.y


def validate_scene_layout(spec: SceneLayoutSpec, narrative: SceneNarrative, profile: ImageSemanticProfile | None) -> list[LayoutIssue]:
    issues: list[LayoutIssue] = []
    content = {item.content_id: item for item in narrative.contents}
    blocks = [*spec.media_blocks, *spec.text_blocks]
    ids = [item.block_id for item in blocks]
    if len(ids) != len(set(ids)):
        issues.append(LayoutIssue(code="duplicate_block_id", severity="critical", message="block IDs must be unique"))
    for media in spec.media_blocks:
        if media.bbox != media.bbox.model_copy(update={"x": 0, "y": 430, "width": 1080, "height": 610}) or media.fit != "contain":
            issues.append(LayoutIssue(code="media_stage_contract", severity="critical", block_id=media.block_id, message="URL media must use the template centered 1080x610 stage with contain fit"))
    for text in spec.text_blocks:
        if text.bbox.x < SAFE or text.bbox.y < SAFE or text.bbox.x + text.bbox.width > 1080 - SAFE or text.bbox.y + text.bbox.height > 1920 - SAFE:
            issues.append(LayoutIssue(code="unsafe_text_margin", block_id=text.block_id, message="text must remain inside the 60px safe area"))
        if text.content_id not in content:
            issues.append(LayoutIssue(code="unknown_content", severity="critical", block_id=text.block_id, message="text references an unknown immutable content ID"))
            continue
        if text.semantic_unit_id != content[text.content_id].semantic_unit_id:
            issues.append(LayoutIssue(code="semantic_unit_mismatch", severity="critical", block_id=text.block_id, message="layout repair cannot switch semantic units"))
        if text.content_hash != content[text.content_id].content_hash(text.variant_id):
            issues.append(LayoutIssue(code="content_hash_mismatch", severity="critical", block_id=text.block_id, message="layout must not rewrite narrative content"))
        value = content[text.content_id].value(text.variant_id)
        if any(phrase not in value for phrase in text.emphasis):
            issues.append(LayoutIssue(code="invalid_emphasis", severity="critical", block_id=text.block_id, message="emphasis must reference exact immutable copy text"))
        if text.max_lines > MAX_LINES[text.typography_role]:
            issues.append(LayoutIssue(code="too_many_lines", block_id=text.block_id, message="role line limit exceeded"))
        # The renderer uses the role minimum; agent cannot express a smaller font.
        if text.typography_role not in MIN_FONT:
            issues.append(LayoutIssue(code="unknown_typography_role", severity="critical", block_id=text.block_id, message="unregistered typography role"))
    overlay = {frozenset(pair) for pair in spec.overlay_policy.allowed_pairs}
    for i, left in enumerate(blocks):
        for right in blocks[i + 1:]:
            if not intersects(left.bbox, right.bbox):
                continue
            pair = frozenset((left.block_id, right.block_id))
            if pair not in overlay:
                issues.append(LayoutIssue(code="undeclared_overlap", block_id=right.block_id, message=f"{left.block_id} overlaps {right.block_id} without overlay policy"))
    if profile:
        protected = profile.subject_bbox
        for text in spec.text_blocks:
            if protected and intersects(text.bbox, protected):
                issues.append(LayoutIssue(code="subject_occlusion", severity="critical", block_id=text.block_id, message="text covers known image subject"))
            if (profile.contains_text or profile.is_screenshot or profile.is_data_chart) and any(intersects(text.bbox, media.bbox) for media in spec.media_blocks):
                issues.append(LayoutIssue(code="dense_media_overlay", block_id=text.block_id, message="text must not overlay a screenshot, chart, or image containing text"))
    return issues


def validate_persistent_title(title: PersistentTitleSpec) -> list[LayoutIssue]:
    issues: list[LayoutIssue] = []
    if title.max_lines > MAX_LINES[TypographyRole.headline]:
        issues.append(LayoutIssue(code="persistent_title_lines", severity="critical", block_id="persistent-title", message="persistent title exceeds headline line limit"))
    if title.z_index < 1:
        issues.append(LayoutIssue(code="persistent_title_layer", severity="critical", block_id="persistent-title", message="persistent title must be above the scene"))
    return issues


def _position(rect) -> tuple[int, int]:
    return (min(2, int((rect.x + rect.width / 2) / 360)), min(2, int((rect.y + rect.height / 2) / 640)))


def normalized_layout_fingerprint(spec: SceneLayoutSpec) -> tuple:
    media = max(spec.media_blocks, key=lambda block: block.bbox.width * block.bbox.height)
    text = max(spec.text_blocks, key=lambda block: block.bbox.width * block.bbox.height) if spec.text_blocks else None
    media_ratio = round((media.bbox.width * media.bbox.height) / (1080 * 1920), 1)
    text_position = _position(text.bbox) if text else None
    alignment = text.alignment if text else "none"
    overlay = bool(text and intersects(media.bbox, text.bbox))
    relation = "overlay" if overlay else "text_above" if text and text.bbox.y < media.bbox.y else "text_below" if text else "media_only"
    return (_position(media.bbox), media_ratio, text_position, alignment, overlay, relation)


def detect_layout_monotony(independent: list[tuple[SceneLayoutSpec, str, ImageSemanticProfile | None]]) -> list[LayoutIssue]:
    states = [(spec, purpose, profile) for spec, purpose, profile in independent if spec.change_mode in {"replace", "adapt", "root"}]
    if len(states) < 4:
        return []
    fingerprints = [normalized_layout_fingerprint(spec) for spec, _, _ in states]
    similar_pairs = 0
    meaningful_pairs = 0
    for index, (_, purpose, profile) in enumerate(states):
        for other_index in range(index + 1, len(states)):
            _, other_purpose, other_profile = states[other_index]
            characteristics_differ = purpose != other_purpose or (profile and other_profile and (profile.is_data_chart != other_profile.is_data_chart or profile.is_screenshot != other_profile.is_screenshot or profile.role != other_profile.role))
            if not characteristics_differ:
                continue
            meaningful_pairs += 1
            similarity = sum(left == right for left, right in zip(fingerprints[index], fingerprints[other_index])) / len(fingerprints[index])
            if similarity >= .83:
                similar_pairs += 1
    if meaningful_pairs >= 3 and similar_pairs / meaningful_pairs >= .75:
        return [LayoutIssue(code="layout_monotony", severity="warning", message="independent layouts remain highly similar despite different purposes or asset characteristics")]
    return []
