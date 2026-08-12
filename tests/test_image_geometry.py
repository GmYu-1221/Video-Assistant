from math import isclose


def contain_geometry(image_width: int, image_height: int, video_width: int, video_height: int) -> tuple[int, int, int, int]:
    scale = min(video_width / image_width, video_height / image_height)
    width = round(image_width * min(1, scale))
    height = round(image_height * min(1, scale))
    return width, height, (video_width - width) // 2, (video_height - height) // 2


def test_common_aspect_ratios_are_contained_without_distortion():
    for iw, ih in ((1920, 1080), (1080, 1920), (1440, 1080), (1080, 1440), (1000, 1000)):
        for vw, vh in ((1920, 1080), (1080, 1920), (1080, 1080)):
            width, height, left, top = contain_geometry(iw, ih, vw, vh)
            assert width <= vw and height <= vh
            assert left >= 0 and top >= 0
            assert isclose(width / height, iw / ih, rel_tol=0.01)
