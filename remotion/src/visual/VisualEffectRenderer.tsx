import React from 'react';
import {useCurrentFrame} from 'remotion';
import type {ReactElement} from 'react';
import type {VisualEvent, AnimationEffect} from '../types';
import {EffectRegistry} from '../effects';
import {TransitionEffectRenderer} from '../transitions/TransitionEffectRenderer';

export const VisualEffectRegistry = {
  ...EffectRegistry,
  glass_shatter_transition: 'glass_shatter_transition',
  shake_transition: 'shake_transition',
  gaussian_blur_transition: 'gaussian_blur_transition',
  directional_blur_transition: 'directional_blur_transition',
  pixel_blur_transition: 'pixel_blur_transition',
  bokeh_blur_transition: 'bokeh_blur_transition',
  water_ripple_transition: 'water_ripple_transition',
} as const;

const sceneEvent = (event: VisualEvent, children: React.ReactNode): ReactElement => {
  const Component = EffectRegistry[event.type as keyof typeof EffectRegistry];
  if (!Component) return <>{children}</>;
  const animation = {asset_id: '', type: event.type, component: event.type, implementation: 'new', duration_frames: event.duration_frames, start_frame: event.start_frame, params: event.params, fallback: 'none'} as AnimationEffect;
  return <Component animation={animation}>{children}</Component>;
};

const EntranceEvent: React.FC<{event: VisualEvent; children?: React.ReactNode}> = ({event, children}) => {
  const frame = useCurrentFrame();
  const endFrame = event.start_frame + event.duration_frames;
  // Mount the effect only for its own lifecycle. Before and after it, the
  // unwrapped image is the static hold: scale 1, rotate 0, translate 0, opacity 1.
  if (frame < event.start_frame || frame >= endFrame) return <>{children}</>;
  return sceneEvent(event, children);
};

export const VisualEffectRenderer = (event: VisualEvent, key: string, children?: React.ReactNode): ReactElement => {
  if (event.phase === 'transition') {
    if (!['card_flip_transition', 'glass_shatter_transition', 'shake_transition', 'gaussian_blur_transition', 'directional_blur_transition', 'pixel_blur_transition', 'bokeh_blur_transition', 'water_ripple_transition'].includes(event.type)) {
      throw new Error(`Unknown visual transition effect: ${event.type}`);
    }
    return TransitionEffectRenderer({from_asset_id: event.source_asset_id ?? '', to_asset_id: event.target_asset_id ?? '', type: event.type as Parameters<typeof TransitionEffectRenderer>[0]['type'], duration_frames: event.duration_frames, params: event.params}, key);
  }
  if (event.phase === 'entrance') {
    return <React.Fragment key={key}><EntranceEvent event={event}>{children}</EntranceEvent></React.Fragment>;
  }
  return <React.Fragment key={key}>{sceneEvent(event, children)}</React.Fragment>;
};
