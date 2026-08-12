export type TransitionType = "fade" | "slide" | "wipe" | "flip" | "zoom_blur";
export type MotionType = "static" | "zoom_in" | "zoom_out" | "pan_left" | "pan_right" | "pan_up" | "pan_down" | "ken_burns";
export interface TransitionConfig { type: TransitionType; duration_frames: number; direction: string; }
export interface ImageAsset { id: string; filename: string; relative_path: string; width: number; height: number; duration_frames: number; motion: MotionType | string; }
export interface AudioConfig { path: string; duration: number; sample_rate: number; bpm: number; }
export interface TimelineItem { asset_id: string; start_frame: number; end_frame: number; duration_frames: number; transition: TransitionConfig; }
export interface VideoOutput { project_dir: string; render_data: string; final_video: string; }
export interface VideoProject { project_id: string; fps: number; width: number; height: number; images: ImageAsset[]; audio: AudioConfig; timeline: TimelineItem[]; output: VideoOutput; media_base_url?: string; }
export type RemotionProps = VideoProject & Record<string, unknown>;
