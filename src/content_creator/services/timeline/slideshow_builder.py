import random
from content_creator.schemas import TimelineItem, TransitionConfig, TransitionType, ImageAsset, TransitionPolicy, PRESETS
from content_creator.services.music.beat_detector import BeatAnalysis


COMPLEXITY = {t: 0.9 for t in TransitionType}
for _type in (TransitionType.fade, TransitionType.crossfade, TransitionType.dissolve, TransitionType.slide, TransitionType.wipe, TransitionType.slide_left, TransitionType.slide_right, TransitionType.wipe_left, TransitionType.wipe_right): COMPLEXITY[_type] = 0.2
for _type in (TransitionType.zoom_in, TransitionType.zoom_out, TransitionType.push_left, TransitionType.push_right, TransitionType.push_up, TransitionType.push_down, TransitionType.circle, TransitionType.iris, TransitionType.rotate): COMPLEXITY[_type] = 0.5
for _type in (TransitionType.flash, TransitionType.glitch, TransitionType.spin, TransitionType.whip, TransitionType.zoom_cut, TransitionType.push): COMPLEXITY[_type] = 0.9

FAST_DURATION = {TransitionType.flash: 3, TransitionType.glitch: 5, TransitionType.spin: 5, TransitionType.whip: 5, TransitionType.zoom_cut: 5, TransitionType.push: 6}


def _choose_types(count: int, policy: TransitionPolicy) -> list[TransitionType]:
    allowed = [t for t in policy.allowed if COMPLEXITY.get(t, 0.9) <= policy.max_complexity] or [TransitionType.fade]
    rng = random.Random(policy.seed)
    chosen: list[TransitionType] = []
    for index in range(count):
        pool = [t for t in allowed if not (policy.avoid_repeat and chosen and t == chosen[-1])]
        if chosen and COMPLEXITY.get(chosen[-1], 0.9) > 0.7:
            pool = [t for t in pool if COMPLEXITY.get(t, 0.9) <= 0.7] or pool
        if not pool: pool = allowed
        if policy.mode == "weighted" and policy.weights:
            weights = [max(1, policy.weights.get(t, 1)) for t in pool]
            selected = rng.choices(pool, weights=weights, k=1)[0]
        elif policy.mode == "random": selected = rng.choice(pool)
        else: selected = pool[index % len(pool)]
        chosen.append(selected)
    return chosen


def build_timeline(images: list[ImageAsset], analysis: BeatAnalysis, fps: int, policy: TransitionPolicy | None = None, style: str = "minimal") -> list[TimelineItem]:
    if not images:
        raise ValueError("at least one image is required")
    beats = analysis.beats or [i * 60.0 / analysis.bpm for i in range(1, 100)]
    candidates = [beats[i] for i in range(0, len(beats), 4)]
    min_seconds, max_seconds = 2 * 60.0 / analysis.bpm, 8 * 60.0 / analysis.bpm
    boundaries = [0.0]
    for index in range(1, len(images)):
        target = analysis.duration * index / len(images)
        nearest = min((b for b in candidates if b - boundaries[-1] >= min_seconds), key=lambda b: abs(b - target), default=target)
        boundaries.append(min(max(nearest, boundaries[-1] + min_seconds), boundaries[-1] + max_seconds))
    boundaries.append(max(analysis.duration, boundaries[-1] + min_seconds))
    policy = policy or TransitionPolicy(allowed=PRESETS.get(style, PRESETS["minimal"]))
    types = _choose_types(max(0, len(images) - 1), policy)
    result: list[TimelineItem] = []
    for index, image in enumerate(images):
        start, end = boundaries[index], min(boundaries[index + 1], analysis.duration)
        if index == len(images) - 1:
            end = max(end, analysis.duration)
        start_frame, end_frame = round(start * fps), max(round(end * fps), round(start * fps) + 1)
        next_duration = max(1, round((boundaries[index + 2] - boundaries[index + 1]) * fps)) if index + 1 < len(images) else end_frame - start_frame
        transition_type = types[index] if index < len(types) else TransitionType.fade
        default_duration = FAST_DURATION.get(transition_type, 6)
        transition_duration = min(default_duration, max(1, (end_frame - start_frame) // 3), next_duration)
        transition = TransitionConfig(type=transition_type, duration_frames=transition_duration, direction="from-right" if index % 2 else "from-left")
        result.append(TimelineItem(asset_id=image.id, start_frame=start_frame, end_frame=end_frame, duration_frames=end_frame - start_frame, transition=transition))
    return result
