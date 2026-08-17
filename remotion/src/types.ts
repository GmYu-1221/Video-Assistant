export type TransitionType = "fade" | "crossfade" | "dissolve" | "slide" | "slide_left" | "slide_right" | "slide_up" | "slide_down" | "wipe" | "wipe_left" | "wipe_right" | "wipe_up" | "wipe_down" | "zoom_in" | "zoom_out" | "flip" | "zoom_blur" | "zoom_crossfade" | "push_left" | "push_right" | "push_up" | "push_down" | "circle" | "rectangle" | "diagonal" | "diagonal_reverse" | "iris" | "radial" | "flip_x" | "flip_y" | "rotate" | "cube_left" | "cube_right" | "blur" | "blur_zoom" | "flash" | "light_leak" | "white_flash" | "black_flash" | "glitch" | "digital_wipe" | "rgb_split" | "scanline" | "push" | "whip" | "stretch_whip" | "liquid" | "zoom_cut" | "spin" | "clock_wipe" | "blinds" | "pixel_reveal";
export interface RGBColor { r: number; g: number; b: number; }
export type MotionType = "static" | "zoom_in" | "zoom_out" | "pan_left" | "pan_right" | "pan_up" | "pan_down" | "ken_burns";
export type EntranceType = "fade" | "fade_scale" | "slide_up" | "none";
export interface EntranceConfig { type: EntranceType | string; durationInFrames: number; }
export interface TransitionConfig { type: TransitionType; duration_frames: number; direction: string; intensity: number; easing: string; background_color?: RGBColor | null; allow_distortion: boolean; }
export type AnimationEffectType = "none" | "card_flip_reveal" | "camera_push" | "glitch_reveal" | "light_leak" | "stretch_reveal" | "elastic_blur_reveal" | "drop_reveal_elastic" | "particle_flip_reveal" | "creative_reveal";
export interface AnimationEffect { asset_id: string; type: AnimationEffectType; component: string; implementation: "custom" | "fallback" | "new"; duration_frames: number; start_frame?: number; params: Record<string, unknown>; fallback: AnimationEffectType; }
export type TransitionEffectType = "card_flip_transition" | "glass_shatter_transition" | "shake_transition" | "gaussian_blur_transition" | "directional_blur_transition" | "pixel_blur_transition" | "bokeh_blur_transition" | "water_ripple_transition" | "zoom_through_transition";
export interface TransitionEffectPlan { from_asset_id: string; to_asset_id: string; type: TransitionEffectType; duration_frames: number; params: {fragment_count?: number; impact_origin?: "center" | "left" | "right" | "top" | "bottom"; blur_type?: "gaussian" | "directional" | "pixelate" | "bokeh" | "mist" | "water_ripple"; direction?: "horizontal" | "vertical" | "radial" | "left" | "right" | "up" | "down" | "center"; intensity?: number; softness?: number; motion_blur?: boolean;}; implementation: "new" | "fallback"; design: Record<string, unknown>; }
export interface TransitionPlanItem { index: number; transition: TransitionConfig; }
export interface TransitionPlan { transitions: TransitionPlanItem[]; }
export interface ImageAsset { id: string; filename: string; relative_path: string; width: number; height: number; fit: "contain"; backgroundColor: RGBColor; duration_frames: number; motion: MotionType | string; entrance: EntranceConfig; }
export interface AudioConfig { path: string; source_path?: string | null; duration: number; sample_rate: number; bpm: number; }
export interface AnimationDesign { description: string; movement: string; direction?: string | null; energy: number; timing?: string | null; camera?: string | null; effects: string[]; }
export type VisualEventPhase = "entrance" | "exit" | "transition" | "camera" | "effect";
export interface VisualEvent { type: string; phase: VisualEventPhase; start_frame: number; duration_frames: number; source_asset_id?: string | null; target_asset_id?: string | null; params: Record<string, unknown>; }
export interface TimelineItem { asset_id: string; start_frame: number; end_frame: number; duration_frames: number; transition: TransitionConfig; visual_events?: VisualEvent[]; animation?: AnimationEffect | null; transition_effect?: TransitionEffectPlan | null; }
export interface VideoOutput { project_dir: string; render_data: string; final_video: string; }
export type VideoCopy = {headline: string; subtitle: string; body: string;}
export type PersistentTitleSpec = {content:string;content_hash:string;bbox:{x:number;y:number;width:number;height:number};alignment:'left'|'center'|'right';typography_role:'headline';font_id:string;style_intent:string;weight:'regular'|'medium'|'bold';color:string;outline:'none'|'dark_thin'|'dark_strong';shadow:'none'|'soft'|'strong';letter_spacing:'normal'|'relaxed';caption_style_intent:'reference_emphasis';max_lines:3;entrance_duration_frames:number;z_index:number};
export interface VideoProject { project_id: string; fps: number; width: number; height: number; images: ImageAsset[]; audio: AudioConfig; timeline: TimelineItem[]; output: VideoOutput; video_copy: VideoCopy; persistent_title?: PersistentTitleSpec | null; media_base_url?: string; }
export type RemotionProps = VideoProject & Record<string, unknown>;
export type VisualSpecKeyframe = {frame: number; value: number; easing?: string};
export type VisualSpecTrack = {target?: string | null; property: string; keyframes: VisualSpecKeyframe[]};
export type VisualSpecRegion = {x: number; y: number; width: number; height: number; overflow?: 'visible' | 'hidden'};
export type VisualSpecTextStyle = {color: string; font_size: number; line_height: number; align?: 'left'|'center'|'right'; font_weight?: number; max_lines: number; top_offset?: number};
export type VisualSpecLayer = {id: string; type: 'image' | 'text' | 'solid' | 'overlay'; region: string; source?: {asset_id?: string; content?: string}; style?: Record<string, unknown>; text_style?: VisualSpecTextStyle; tracks?: VisualSpecTrack[]};
export type VisualSpecScene = {id: string; start_frame: number; duration_frames: number; layers: VisualSpecLayer[]};
export type VisualSpecTransition = {id: string; from_scene: string; to_scene: string; start_frame: number; duration_frames: number; preset?: string | null; params?: Record<string, number | string>; tracks?: VisualSpecTrack[]};
export type VisualSpec = {version: '2.0'; composition: {width: number; height: number; fps: number; duration_frames: number; background?: string}; layout: {preset: string; regions: Record<string, VisualSpecRegion>}; persistent_layers?: VisualSpecLayer[]; scenes: VisualSpecScene[]; transitions?: VisualSpecTransition[]};
export interface RemotionPropsWithVisualSpec extends RemotionProps {visual_spec?: VisualSpec}
