export type TransitionImplementation = 'native' | 'custom' | 'fallback';
export type TransitionMetadata = {implementation: TransitionImplementation; complexity: number; defaultDurationFrames: number; supportedDirections: string[]; usesMask: boolean; usesTransform: boolean};
const custom = (complexity: number, duration: number, usesMask = false, usesTransform = false): TransitionMetadata => ({implementation:'custom', complexity, defaultDurationFrames:duration, supportedDirections:['from-left','from-right'], usesMask, usesTransform});
export const TransitionMetadataRegistry: Record<string, TransitionMetadata> = {
  fade: {implementation:'native', complexity:.1, defaultDurationFrames:6, supportedDirections:[], usesMask:false, usesTransform:false},
  slide: {implementation:'native', complexity:.3, defaultDurationFrames:6, supportedDirections:['from-left','from-right'], usesMask:false, usesTransform:true},
  slide_left: {implementation:'native', complexity:.3, defaultDurationFrames:6, supportedDirections:['from-left'], usesMask:false, usesTransform:true},
  slide_right: {implementation:'native', complexity:.3, defaultDurationFrames:6, supportedDirections:['from-right'], usesMask:false, usesTransform:true},
  wipe: {implementation:'native', complexity:.3, defaultDurationFrames:6, supportedDirections:['from-left','from-right'], usesMask:true, usesTransform:false},
  wipe_left: {implementation:'native', complexity:.3, defaultDurationFrames:6, supportedDirections:['from-left'], usesMask:true, usesTransform:false},
  wipe_right: {implementation:'native', complexity:.3, defaultDurationFrames:6, supportedDirections:['from-right'], usesMask:true, usesTransform:false},
  flip: {implementation:'native', complexity:.5, defaultDurationFrames:6, supportedDirections:['from-left','from-right'], usesMask:false, usesTransform:true},
  zoom_blur: {implementation:'native', complexity:.6, defaultDurationFrames:6, supportedDirections:[], usesMask:false, usesTransform:true},
  crossfade: custom(.2,8), black_flash: custom(.8,4), white_flash: custom(.9,3), push: custom(.5,6,false,true), whip: custom(.8,5,false,true), digital_wipe: custom(.6,6,true), iris: custom(.5,8,true), clock_wipe: custom(.6,8,true), blinds: custom(.6,8,true), pixel_reveal: custom(.7,6), glitch: custom(.9,5,false,true), light_leak: custom(.7,5),
};
const fallback: TransitionMetadata = {implementation:'fallback', complexity:.2, defaultDurationFrames:6, supportedDirections:['from-left','from-right'], usesMask:false, usesTransform:false};
for (const legacy of ['dissolve','slide_up','slide_down','wipe_up','wipe_down','zoom_in','zoom_out','zoom_crossfade','push_left','push_right','push_up','push_down','circle','rectangle','diagonal','diagonal_reverse','radial','flip_x','flip_y','rotate','cube_left','cube_right','blur','blur_zoom','flash','rgb_split','scanline','zoom_cut','spin']) TransitionMetadataRegistry[legacy] = fallback;
export const isRealTransition = (type: string): boolean => ['native','custom'].includes(TransitionMetadataRegistry[type]?.implementation ?? 'fallback');
