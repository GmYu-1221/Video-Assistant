import subprocess
from pathlib import Path
from content_creator.services.music.audio_adapter import adapt_audio_to_duration

def test_audio_adapter_loops_and_trims(tmp_path: Path):
    source = tmp_path / "source.wav"; output = tmp_path / "adapted.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(source)], check=True)
    adapt_audio_to_duration(source, 2.5, output)
    probe = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(output)], text=True)
    assert abs(float(probe.strip()) - 2.5) < 0.05
