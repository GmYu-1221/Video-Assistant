from content_creator.schemas import TimelineItem, TransitionConfig, TransitionType, ImageAsset
from content_creator.services.music.beat_detector import BeatAnalysis


def build_timeline(images: list[ImageAsset], analysis: BeatAnalysis, fps: int) -> list[TimelineItem]:
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
    types = [TransitionType.fade, TransitionType.slide, TransitionType.wipe, TransitionType.zoom_blur, TransitionType.flip]
    result: list[TimelineItem] = []
    for index, image in enumerate(images):
        start, end = boundaries[index], min(boundaries[index + 1], analysis.duration)
        if index == len(images) - 1:
            end = max(end, analysis.duration)
        start_frame, end_frame = round(start * fps), max(round(end * fps), round(start * fps) + 1)
        transition = TransitionConfig(type=types[index % len(types)], duration_frames=min(round(0.4 * fps), max(1, (end_frame - start_frame) // 3)), direction="from-right" if index % 2 else "from-left")
        result.append(TimelineItem(asset_id=image.id, start_frame=start_frame, end_frame=end_frame, duration_frames=end_frame - start_frame, transition=transition))
    return result
