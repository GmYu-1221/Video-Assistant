from enum import Enum
from pydantic import BaseModel, Field


class TransitionType(str, Enum):
    fade = "fade"
    crossfade = "crossfade"
    dissolve = "dissolve"
    slide = "slide"
    slide_left = "slide_left"
    slide_right = "slide_right"
    slide_up = "slide_up"
    slide_down = "slide_down"
    wipe = "wipe"
    wipe_left = "wipe_left"
    wipe_right = "wipe_right"
    wipe_up = "wipe_up"
    wipe_down = "wipe_down"
    zoom_in = "zoom_in"
    zoom_out = "zoom_out"
    flip = "flip"
    zoom_blur = "zoom_blur"
    zoom_crossfade = "zoom_crossfade"
    push_left = "push_left"
    push_right = "push_right"
    push_up = "push_up"
    push_down = "push_down"
    circle = "circle"
    rectangle = "rectangle"
    diagonal = "diagonal"
    diagonal_reverse = "diagonal_reverse"
    iris = "iris"
    radial = "radial"
    flip_x = "flip_x"
    flip_y = "flip_y"
    rotate = "rotate"
    cube_left = "cube_left"
    cube_right = "cube_right"
    blur = "blur"
    blur_zoom = "blur_zoom"
    flash = "flash"
    light_leak = "light_leak"
    white_flash = "white_flash"
    black_flash = "black_flash"
    glitch = "glitch"
    digital_wipe = "digital_wipe"
    rgb_split = "rgb_split"
    scanline = "scanline"
    push = "push"
    whip = "whip"
    zoom_cut = "zoom_cut"
    spin = "spin"


class TransitionConfig(BaseModel):
    type: TransitionType = TransitionType.fade
    duration_frames: int = Field(default=6, ge=1)
    direction: str = "from-right"
    intensity: float = Field(default=0.6, ge=0, le=1)
    easing: str = "easeInOut"

    @property
    def duration(self) -> int:
        return self.duration_frames
