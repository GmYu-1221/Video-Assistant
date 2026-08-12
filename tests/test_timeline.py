from content_creator.schemas import ImageAsset
from content_creator.services.music.beat_detector import BeatAnalysis
from content_creator.services.timeline import build_timeline

def test_timeline_has_ordered_frames():
    images=[ImageAsset(id=str(i),filename=f'{i}.jpg',relative_path=f'{i}.jpg',width=10,height=10) for i in range(3)]
    timeline=build_timeline(images,BeatAnalysis(12,8000,120,list(i*.5 for i in range(24)),list(i*2 for i in range(6))),30)
    assert len(timeline)==3 and all(x.end_frame>x.start_frame for x in timeline)

def test_short_bgm_does_not_compress_ten_images():
    images=[ImageAsset(id=str(i),filename=f'{i}.jpg',relative_path=f'{i}.jpg',width=10,height=10) for i in range(10)]
    timeline=build_timeline(images, BeatAnalysis(8,8000,120,[i*.5 for i in range(16)],[i*2 for i in range(4)]),30)
    assert min(item.duration_frames for item in timeline) >= 60
    assert timeline[-1].end_frame == max(item.end_frame for item in timeline)
