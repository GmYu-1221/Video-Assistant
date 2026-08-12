from pathlib import Path
import subprocess

def adapt_audio_to_duration(source_audio: str | Path, target_duration: float, output_audio: str | Path, fade_seconds: float = 0.75) -> Path:
    if target_duration <= 0: raise ValueError("target_duration must be positive")
    source, output = Path(source_audio).resolve(), Path(output_audio)
    output.parent.mkdir(parents=True, exist_ok=True)
    if source == output.resolve(): raise ValueError("output_audio must differ from source_audio")
    fade = min(max(fade_seconds, 0.0), target_duration / 2)
    filters = [f"atrim=duration={target_duration:.6f}", "asetpts=N/SR/TB"]
    if fade > 0: filters.append(f"afade=t=out:st={target_duration-fade:.6f}:d={fade:.6f}")
    command = ["ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "-1", "-i", str(source), "-t", f"{target_duration:.6f}", "-af", ",".join(filters), "-ar", "44100", "-ac", "2", str(output)]
    result = subprocess.run(command, check=False)
    if result.returncode or not output.is_file() or output.stat().st_size == 0: raise RuntimeError("ffmpeg failed to adapt audio")
    return output
