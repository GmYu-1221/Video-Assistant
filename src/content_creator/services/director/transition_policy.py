"""Deterministic, beat-aware safety policy for Director transitions."""

from __future__ import annotations

import random

from content_creator.schemas import DirectorPlan, TransitionConfig, TransitionType
from content_creator.services.timeline.slideshow_builder import FAST_DURATION, REAL_TRANSITIONS


DEFAULT_DURATION = {
    TransitionType.fade: 8,
    TransitionType.crossfade: 8,
    TransitionType.push: 6,
    TransitionType.whip: 5,
    TransitionType.glitch: 5,
    TransitionType.flash: 3,
    TransitionType.iris: 8,
}

LOW_POOL = (TransitionType.fade, TransitionType.crossfade)
MEDIUM_POOL = (TransitionType.push, TransitionType.digital_wipe)
HIGH_POOL = (TransitionType.whip, TransitionType.glitch, TransitionType.flash)
CLIMAX_POOL = (TransitionType.iris, TransitionType.white_flash)


def _strength_at(strengths: list[float] | None, index: int) -> float:
    if not strengths:
        return 0.35 if index % 2 == 0 else 0.65
    return max(0.0, min(1.0, float(strengths[min(index, len(strengths) - 1)])))


def _pool_for_strength(value: float, index: int, total: int) -> tuple[TransitionType, ...]:
    if index == 0:
        return LOW_POOL
    if index == total - 1 and value >= 0.75:
        return CLIMAX_POOL
    if value >= 0.72:
        return HIGH_POOL
    if value >= 0.42:
        return MEDIUM_POOL
    return LOW_POOL


def build_transition_sequence(count: int, beat_strengths: list[float] | None = None, seed: int = 0) -> list[TransitionType]:
    """Create a varied sequence for ``count`` scenes (one transition per scene)."""
    if count <= 0:
        return []
    rng = random.Random(seed)
    selected: list[TransitionType] = []
    for index in range(count):
        pool = list(_pool_for_strength(_strength_at(beat_strengths, index), index, count))
        if selected:
            pool = [item for item in pool if item != selected[-1]] or pool
        if len(selected) >= 2 and selected[-1] == selected[-2]:
            pool = [item for item in pool if item != selected[-1]] or list(MEDIUM_POOL)
        selected.append(rng.choice(pool))

    # A short/flat beat analysis should still yield cinematic variety.
    if count >= 7 and len(set(selected)) < 4:
        required = [TransitionType.crossfade, TransitionType.push, TransitionType.whip, TransitionType.iris]
        for index, transition in enumerate(required):
            if transition not in selected:
                replace_at = min(index + 1, count - 1)
                if replace_at and selected[replace_at] == selected[replace_at - 1]:
                    replace_at = (replace_at + 1) % count
                selected[replace_at] = transition
    return selected


def _duration_for(transition: TransitionType, requested: int) -> int:
    maximum = DEFAULT_DURATION.get(transition, FAST_DURATION.get(transition, 6))
    return max(1, min(requested, maximum))


def apply_transition_policy(plan: DirectorPlan, beat_strengths: list[float] | None = None, seed: int = 0) -> DirectorPlan:
    """Repair unsafe/repetitive plans while retaining valid director choices."""
    items = list(plan.timeline)
    if not items:
        return plan
    fade_count = sum(item.transition.type == TransitionType.fade for item in items)
    needs_variety = len(items) >= 7 and (len({item.transition.type for item in items}) < 4 or fade_count / len(items) > 0.30)
    rng = random.Random(seed)
    previous: list[TransitionType] = []
    repaired = []
    for index, item in enumerate(items):
        transition = item.transition.type
        invalid = transition not in REAL_TRANSITIONS
        duplicate = len(previous) >= 2 and previous[-1] == previous[-2] == transition
        excessive_fade = transition == TransitionType.fade and fade_count / len(items) > 0.30
        if invalid or duplicate or excessive_fade or (needs_variety and index == 0 and transition != TransitionType.fade):
            candidates = list(_pool_for_strength(_strength_at(beat_strengths, index), index, len(items)))
            candidates = [candidate for candidate in candidates if candidate not in previous[-2:]] or candidates
            transition = rng.choice(candidates)
        duration = _duration_for(transition, item.transition.duration_frames)
        updated = item.model_copy(update={"transition": TransitionConfig(type=transition, duration_frames=duration, direction=item.transition.direction, intensity=item.transition.intensity, easing=item.transition.easing, background_color=item.transition.background_color, allow_distortion=transition in {TransitionType.stretch_whip, TransitionType.liquid, TransitionType.glitch, TransitionType.whip})})
        repaired.append(updated)
        previous.append(transition)
    return plan.model_copy(update={"timeline": repaired})
