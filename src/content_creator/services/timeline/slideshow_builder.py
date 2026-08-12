import random
from dataclasses import dataclass
from content_creator.schemas import ImageAsset, PRESETS, TransitionConfig, TransitionPolicy, TransitionType, TimelineItem
from content_creator.services.music.beat_detector import BeatAnalysis

COMPLEXITY = {t: 0.9 for t in TransitionType}
for t in (TransitionType.fade, TransitionType.crossfade, TransitionType.dissolve, TransitionType.slide, TransitionType.wipe, TransitionType.slide_left, TransitionType.slide_right, TransitionType.wipe_left, TransitionType.wipe_right): COMPLEXITY[t] = 0.2
for t in (TransitionType.zoom_in, TransitionType.zoom_out, TransitionType.push_left, TransitionType.push_right, TransitionType.push_up, TransitionType.push_down, TransitionType.circle, TransitionType.iris, TransitionType.rotate): COMPLEXITY[t] = 0.5
COMPLEXITY[TransitionType.zoom_cut] = 1.1
FAST_DURATION = {TransitionType.crossfade: 8, TransitionType.black_flash: 4, TransitionType.white_flash: 3, TransitionType.push: 6, TransitionType.whip: 5, TransitionType.stretch_whip: 6, TransitionType.digital_wipe: 6, TransitionType.iris: 8, TransitionType.clock_wipe: 8, TransitionType.blinds: 8, TransitionType.pixel_reveal: 6, TransitionType.glitch: 5, TransitionType.light_leak: 5, TransitionType.flash: 3, TransitionType.spin: 5, TransitionType.zoom_cut: 5}
REAL_TRANSITIONS = {TransitionType.fade, TransitionType.crossfade, TransitionType.black_flash, TransitionType.white_flash, TransitionType.flash, TransitionType.push, TransitionType.whip, TransitionType.stretch_whip, TransitionType.digital_wipe, TransitionType.iris, TransitionType.clock_wipe, TransitionType.blinds, TransitionType.pixel_reveal, TransitionType.glitch, TransitionType.light_leak, TransitionType.zoom_cut, TransitionType.slide, TransitionType.slide_left, TransitionType.slide_right, TransitionType.wipe, TransitionType.wipe_left, TransitionType.wipe_right, TransitionType.flip, TransitionType.zoom_blur}

@dataclass(frozen=True)
class ImageDurationPolicy:
    min_beats: int = 2
    default_beats: int = 4
    max_beats: int = 8
    def calculate_beats(self, _asset: ImageAsset, _analysis: BeatAnalysis) -> int:
        return max(self.min_beats, min(self.default_beats, self.max_beats))

def _choose_types(count: int, policy: TransitionPolicy) -> list[TransitionType]:
    allowed = [t for t in policy.allowed if t in REAL_TRANSITIONS and COMPLEXITY.get(t, 0.9) <= policy.max_complexity] or [TransitionType.fade]
    rng = random.Random(policy.seed); chosen: list[TransitionType] = []
    for index in range(count):
        pool = [t for t in allowed if not (policy.avoid_repeat and chosen and t == chosen[-1])]
        if chosen and COMPLEXITY.get(chosen[-1], 0.9) > 0.7: pool = [t for t in pool if COMPLEXITY.get(t, 0.9) < 0.5] or pool
        if not pool: pool = allowed
        selected = rng.choices(pool, weights=[max(1, policy.weights.get(t, 1)) for t in pool], k=1)[0] if policy.mode == "weighted" and policy.weights else (rng.choice(pool) if policy.mode == "random" else pool[index % len(pool)])
        chosen.append(selected)
    return chosen

def build_timeline(images: list[ImageAsset], analysis: BeatAnalysis, fps: int, policy: TransitionPolicy | None = None, style: str = "minimal", duration_policy: ImageDurationPolicy | None = None) -> list[TimelineItem]:
    if not images: raise ValueError("at least one image is required")
    duration_policy = duration_policy or ImageDurationPolicy(); beat_seconds = 60.0 / max(analysis.bpm, 1.0)
    scene_frames = [max(1, round(duration_policy.calculate_beats(asset, analysis) * beat_seconds * fps)) for asset in images]
    types = _choose_types(max(0, len(images) - 1), policy or TransitionPolicy(allowed=PRESETS.get(style, PRESETS["minimal"])))
    result: list[TimelineItem] = []; cursor = 0
    for index, (image, frames) in enumerate(zip(images, scene_frames)):
        transition_type = types[index] if index < len(types) else TransitionType.fade
        transition_frames = min(FAST_DURATION.get(transition_type, 6), max(1, frames // 3))
        result.append(TimelineItem(asset_id=image.id, start_frame=cursor, end_frame=cursor + frames, duration_frames=frames, transition=TransitionConfig(type=transition_type, duration_frames=transition_frames, direction="from-right" if index % 2 else "from-left", allow_distortion=transition_type in {TransitionType.stretch_whip, TransitionType.glitch, TransitionType.whip})))
        cursor += frames
    return result
