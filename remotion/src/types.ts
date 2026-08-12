export type TransitionType = "fade" | "crossfade" | "dissolve" | "slide" | "slide_left" | "slide_right" | "slide_up" | "slide_down" | "wipe" | "wipe_left" | "wipe_right" | "wipe_up" | "wipe_down" | "zoom_in" | "zoom_out" | "flip" | "zoom_blur" | "zoom_crossfade" | "push_left" | "push_right" | "push_up" | "push_down" | "circle" | "rectangle" | "diagonal" | "diagonal_reverse" | "iris" | "radial" | "flip_x" | "flip_y" | "rotate" | "cube_left" | "cube_right" | "blur" | "blur_zoom" | "flash" | "light_leak" | "white_flash" | "black_flash" | "glitch" | "digital_wipe" | "rgb_split" | "scanline" | "push" | "whip" | "zoom_cut" | "spin";
export type MotionType = "static" | "zoom_in" | "zoom_out" | "pan_left" | "pan_right" | "pan_up" | "pan_down" | "ken_burns";
export type EntranceType = "fade" | "fade_scale" | "slide_up" | "none";
export interface EntranceConfig { type: EntranceType | string; durationInFrames: number; }
export interface TransitionConfig { type: TransitionType; duration_frames: number; direction: string; intensity: number; easing: string; }
export interface TransitionPlanItem { index: number; transition: TransitionConfig; }
export interface TransitionPlan { transitions: TransitionPlanItem[]; }
export interface ImageAsset { id: string; filename: string; relative_path: string; width: number; height: number; fit: "contain"; duration_frames: number; motion: MotionType | string; entrance: EntranceConfig; }
export interface AudioConfig { path: string; duration: number; sample_rate: number; bpm: number; }
export interface TimelineItem { asset_id: string; start_frame: number; end_frame: number; duration_frames: number; transition: TransitionConfig; }
export interface VideoOutput { project_dir: string; render_data: string; final_video: string; }
export interface VideoProject { project_id: string; fps: number; width: number; height: number; images: ImageAsset[]; audio: AudioConfig; timeline: TimelineItem[]; output: VideoOutput; media_base_url?: string; }
export type RemotionProps = VideoProject & Record<string, unknown>;
