import type {TemplatePresentationComponent} from './types';
import {Qwen38Transition} from './qwen3-8';
import {ZoomWhipV2Transition} from './zoom-whip-v2';

export const TemplatePresentationRegistry: Record<string, TemplatePresentationComponent> = {
  qwen3_8: Qwen38Transition,
  zoom_whip_v2: ZoomWhipV2Transition,
};
