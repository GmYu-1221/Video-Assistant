import wave, struct
from content_creator.services.music import analyze_audio

def test_wav_fallback_or_analysis(tmp_path):
    path=tmp_path/'a.wav'
    with wave.open(str(path),'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(struct.pack('<h',0)*8000)
    result=analyze_audio(str(path)); assert result.duration == 1; assert result.bpm > 0; assert result.beats
