import type {TemplatePresentationComponent} from './types';
import {Qwen38Transition} from './qwen3-8';

export const TemplatePresentationRegistry: Record<string, TemplatePresentationComponent> = {
  qwen3_8: Qwen38Transition,
};
