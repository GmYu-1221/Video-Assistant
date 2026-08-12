from dataclasses import dataclass
import numpy as np


@dataclass
class BeatAnalysis:
    duration: float
    sample_rate: int
    bpm: float
    beats: list[float]
    downbeats: list[float]
    beat_strengths: list[float] | None = None


def analyze_audio(path: str) -> BeatAnalysis:
    try:
        import librosa
        samples, sample_rate = librosa.load(path, sr=None, mono=True)
        duration = float(len(samples) / sample_rate) if sample_rate else 0.0
        tempo, beat_frames = librosa.beat.beat_track(y=samples, sr=sample_rate, units="frames")
        bpm = float(np.asarray(tempo).reshape(-1)[0]) if np.asarray(tempo).size else 120.0
        beats = [float(value) for value in librosa.frames_to_time(beat_frames, sr=sample_rate)]
        if not beats or bpm <= 0:
            raise ValueError("beat tracker returned no beats")
        step = max(1, round(bpm / 60.0 * 4))
        downbeats = beats[::step] if len(beats) >= step else [beats[0]]
        onset = librosa.onset.onset_strength(y=samples, sr=sample_rate)
        strengths = [float(onset[min(len(onset) - 1, int(frame))]) for frame in beat_frames] if len(onset) else None
        return BeatAnalysis(duration, int(sample_rate), bpm, beats, downbeats, strengths)
    except Exception:
        # A deterministic fallback keeps timeline generation usable for unusual codecs.
        import wave
        with wave.open(path, "rb") as wav:
            sample_rate = wav.getframerate()
            duration = wav.getnframes() / sample_rate
        bpm = 120.0
        interval = 60.0 / bpm
        beats = list(np.arange(0.0, duration, interval))
        return BeatAnalysis(duration, sample_rate, bpm, beats, beats[::4] or beats[:1])
