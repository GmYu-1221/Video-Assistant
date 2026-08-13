"""Export the Python protocol as a TypeScript declaration."""
from pathlib import Path
from .project import VideoProject
from .transition import TransitionType


TS_TYPES = '''export type TransitionType = __TRANSITION_TYPES__;
export interface RGBColor { r: number; g: number; b: number; }
export type MotionType = "static" | "zoom_in" | "zoom_out" | "pan_left" | "pan_right" | "pan_up" | "pan_down" | "ken_burns";
export type EntranceType = "fade" | "fade_scale" | "slide_up" | "none";
export interface EntranceConfig { type: EntranceType | string; durationInFrames: number; }
export interface TransitionConfig { type: TransitionType; duration_frames: number; direction: string; intensity: number; easing: string; background_color?: RGBColor | null; allow_distortion: boolean; }
export type AnimationEffectType = "none" | "card_flip_reveal" | "camera_push" | "glitch_reveal" | "light_leak" | "stretch_reveal" | "drop_reveal_elastic" | "particle_flip_reveal" | "creative_reveal";
export interface AnimationEffect { asset_id: string; type: AnimationEffectType; component: string; implementation: "custom" | "fallback" | "new"; duration_frames: number; params: Record<string, unknown>; fallback: AnimationEffectType; }
export type TransitionEffectType = "card_flip_transition" | "glass_shatter_transition" | "shake_transition" | "gaussian_blur_transition" | "directional_blur_transition" | "pixel_blur_transition" | "bokeh_blur_transition" | "water_ripple_transition";
export interface TransitionEffectPlan { from_asset_id: string; to_asset_id: string; type: TransitionEffectType; duration_frames: number; params: {fragment_count?: number; impact_origin?: "center" | "left" | "right" | "top" | "bottom"; blur_type?: "gaussian" | "directional" | "pixelate" | "bokeh" | "mist" | "water_ripple"; direction?: "horizontal" | "vertical" | "radial" | "left" | "right" | "up" | "down"; intensity?: number; softness?: number; motion_blur?: boolean;}; implementation: "new" | "fallback"; design: Record<string, unknown>; }
export interface TransitionPlanItem { index: number; transition: TransitionConfig; }
export interface TransitionPlan { transitions: TransitionPlanItem[]; }
export interface ImageAsset { id: string; filename: string; relative_path: string; width: number; height: number; fit: "contain"; backgroundColor: RGBColor; duration_frames: number; motion: MotionType | string; entrance: EntranceConfig; }
export interface AudioConfig { path: string; source_path?: string | null; duration: number; sample_rate: number; bpm: number; }
export interface TimelineItem { asset_id: string; start_frame: number; end_frame: number; duration_frames: number; transition: TransitionConfig; animation?: AnimationEffect | null; transition_effect?: TransitionEffectPlan | null; }
export interface VideoOutput { project_dir: string; render_data: string; final_video: string; }
export interface VideoProject { project_id: string; fps: number; width: number; height: number; images: ImageAsset[]; audio: AudioConfig; timeline: TimelineItem[]; output: VideoOutput; media_base_url?: string; }
export type RemotionProps = VideoProject & Record<string, unknown>;
'''


def export_types(path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    transition_types = " | ".join(f'"{item.value}"' for item in TransitionType)
    target.write_text(TS_TYPES.replace("__TRANSITION_TYPES__", transition_types), encoding="utf-8")
    return target


def validate_project(data: dict) -> VideoProject:
    return VideoProject.model_validate(data)
