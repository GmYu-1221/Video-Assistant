from content_creator.schemas import ImageAsset
from content_creator.services.music.beat_detector import BeatAnalysis
from content_creator.services.timeline import build_timeline

def test_timeline_has_ordered_frames():
    images=[ImageAsset(id=str(i),filename=f'{i}.jpg',relative_path=f'{i}.jpg',width=10,height=10) for i in range(3)]
    timeline=build_timeline(images,BeatAnalysis(12,8000,120,list(i*.5 for i in range(24)),list(i*2 for i in range(6))),30)
    assert len(timeline)==3 and all(x.end_frame>x.start_frame for x in timeline)
