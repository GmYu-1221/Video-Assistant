"""Compatibility helpers for the qwen-only transition policy.

Scene continuity now decides whether a boundary is continuous, accent, or a
scene cut. Concrete scene-cut rendering is handled by the qwen3_8 template;
there is no legacy transition selection here.
"""

from __future__ import annotations

from content_creator.schemas import DirectorPlan


def build_transition_sequence(count: int, beat_strengths=None, seed: int = 0) -> list[None]:
    """Return boundary placeholders for callers of the removed API."""
    return [None for _ in range(max(0, count))]


def apply_transition_policy(plan: DirectorPlan, beat_strengths=None, seed: int = 0) -> DirectorPlan:
    """Preserve the Director plan; transition type repair no longer exists."""
    return plan
