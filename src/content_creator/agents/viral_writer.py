"""Reusable Viral Writer guidance and grounded copy helpers."""
from __future__ import annotations

import re
from pathlib import Path


def viral_writer_skill_path() -> Path:
    return Path(__file__).resolve().parents[3] / ".agents" / "skills" / "viral-writer" / "SKILL.md"


def load_viral_writer_skill() -> str:
    path = viral_writer_skill_path()
    if not path.is_file():
        raise RuntimeError("Copy Fitting Agent requires the Viral Writer skill")
    return path.read_text(encoding="utf-8")


def article_sentences(text: str) -> list[str]:
    boilerplate = ("当前文章被以下社区和专栏收录", "作者 |", "出品 |", "版权声明", "免责声明")
    ui_tokens = ("评论", "分享", "复制链接", "扫一扫", "举报", "收藏")
    parts = [re.sub(r"\s+", " ", part).strip() for part in re.split(r"(?<=[。！？!?])\s*|\n+", text)]
    return [part for part in parts if len(part) >= 12 and not any(token in part for token in boilerplate) and not any(token in part for token in ui_tokens)]


def build_variants(text: str) -> tuple[str, str, str] | None:
    """Keep the established full/short/micro copy fitting behavior."""
    clean = re.sub(r"\s+", " ", text).strip()[:800]
    if len(clean) < 12:
        return None
    targets = (min(400, max(10, int(len(clean) * .7))), min(180, max(8, int(len(clean) * .4))))

    def cut(target: int, hard_limit: int) -> str:
        window = clean[:target]
        boundaries = [match.end() for match in re.finditer(r"[，、；：。！？,.!?;:]|\s+", window) if match.end() >= max(4, target // 2)]
        index = boundaries[-1] if boundaries else min(target, hard_limit - 1)
        return clean[:index].rstrip(" ，、；：。！？") + "…"

    short = cut(targets[0], len(clean))
    micro = cut(min(targets[1], len(short) - 1), len(short))
    return (clean, short, micro) if len(clean) > len(short) > len(micro) else None
