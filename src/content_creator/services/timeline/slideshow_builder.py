from dataclasses import dataclass
from content_creator.schemas import ImageAsset, PRESETS, TransitionConfig, TransitionPolicy, TransitionType, TimelineItem
from content_creator.services.music.beat_detector import BeatAnalysis

FAST_DURATION = {}

@dataclass(frozen=True)
class ImageDurationPolicy:
    min_beats: int = 2
    default_beats: int = 4
    max_beats: int = 8
    def calculate_beats(self, _asset: ImageAsset, _analysis: BeatAnalysis) -> int:
        return max(self.min_beats, min(self.default_beats, self.max_beats))

def build_timeline(images: list[ImageAsset], analysis: BeatAnalysis, fps: int, policy: TransitionPolicy | None = None, style: str = "minimal", duration_policy: ImageDurationPolicy | None = None) -> list[TimelineItem]:
    if not images: raise ValueError("at least one image is required")
    duration_policy = duration_policy or ImageDurationPolicy(); beat_seconds = 60.0 / max(analysis.bpm, 1.0)
    scene_frames = [max(1, round(duration_policy.calculate_beats(asset, analysis) * beat_seconds * fps)) for asset in images]
    result: list[TimelineItem] = []; cursor = 0
    for index, (image, frames) in enumerate(zip(images, scene_frames)):
        # Scene boundaries are resolved later from Director continuity. The
        # legacy transition field is retained only for old Python callers and
        # is excluded from render_data serialization.
        result.append(TimelineItem(asset_id=image.id, start_frame=cursor, end_frame=cursor + frames, duration_frames=frames, transition=TransitionConfig()))
        cursor += frames
    return result
