import React from 'react';
import type {AnimationEffect} from '../types';
import {CameraPush} from './CameraPush';
import {CardFlipReveal} from './CardFlipReveal';
import {GlitchReveal} from './GlitchReveal';
import {LightLeak} from './LightLeak';

export const EffectRegistry = {
  card_flip_reveal: CardFlipReveal,
  camera_push: CameraPush,
  glitch_reveal: GlitchReveal,
  light_leak: LightLeak,
} as const;

export const EffectRenderer: React.FC<{animation: AnimationEffect | null | undefined; children: React.ReactNode}> = ({animation, children}) => {
  if (!animation || animation.implementation === 'fallback' || animation.effect === 'none') return <>{children}</>;
  const Component = EffectRegistry[animation.effect as keyof typeof EffectRegistry];
  return <Component animation={animation}>{children}</Component>;
};
