import React from 'react';
import type {ReactElement} from 'react';
import type {VisualEvent, AnimationEffect} from '../types';
import {EffectRegistry} from '../effects';
import {TransitionEffectRenderer} from '../transitions/TransitionEffectRenderer';

export const VisualEffectRegistry = {
  ...EffectRegistry,
  glass_shatter_transition: 'glass_shatter_transition',
  shake_transition: 'shake_transition',
} as const;

const sceneEvent = (event: VisualEvent, children: React.ReactNode): ReactElement => {
  const Component = EffectRegistry[event.type as keyof typeof EffectRegistry];
  if (!Component) return <>{children}</>;
  const animation = {asset_id: '', type: event.type, component: event.type, implementation: 'new', duration_frames: event.duration_frames, params: event.params, fallback: 'none'} as AnimationEffect;
  return <Component animation={animation}>{children}</Component>;
};

export const VisualEffectRenderer = (event: VisualEvent, key: string, children?: React.ReactNode): ReactElement => {
  if (event.phase === 'transition') {
    if (event.type !== 'card_flip_transition' && event.type !== 'glass_shatter_transition' && event.type !== 'shake_transition') {
      throw new Error(`Unknown visual transition effect: ${event.type}`);
    }
    return TransitionEffectRenderer({from_asset_id: event.source_asset_id ?? '', to_asset_id: event.target_asset_id ?? '', type: event.type as 'card_flip_transition' | 'glass_shatter_transition' | 'shake_transition', duration_frames: event.duration_frames, params: event.params}, key);
  }
  return <React.Fragment key={key}>{sceneEvent(event, children)}</React.Fragment>;
};
