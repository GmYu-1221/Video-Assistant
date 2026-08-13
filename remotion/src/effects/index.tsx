import React from 'react';
import type {AnimationEffect} from '../types';
import {CameraPush} from './CameraPush';
import {CardFlipReveal} from './CardFlipReveal';
import {GlitchReveal} from './GlitchReveal';
import {LightLeak} from './LightLeak';
import {StretchReveal} from './StretchReveal';
import {ElasticBlurReveal} from './ElasticBlurReveal';
import {DropRevealElastic} from './DropRevealElastic';
import {ParticleFlipReveal} from './ParticleFlipReveal';
import {CreativeReveal} from './CreativeReveal';

export const EffectRegistry = {
  card_flip_reveal: CardFlipReveal,
  camera_push: CameraPush,
  glitch_reveal: GlitchReveal,
  light_leak: LightLeak,
  stretch_reveal: StretchReveal,
  elastic_blur_reveal: ElasticBlurReveal,
  drop_reveal_elastic: DropRevealElastic,
  particle_flip_reveal: ParticleFlipReveal,
  creative_reveal: CreativeReveal,
} as const;

export const EffectRenderer: React.FC<{animation: AnimationEffect | null | undefined; children: React.ReactNode}> = ({animation, children}) => {
  if (!animation || animation.type === 'none') return <>{children}</>;
  const Component = EffectRegistry[animation.type as keyof typeof EffectRegistry];
  if (!Component) return <CreativeReveal animation={animation}>{children}</CreativeReveal>;
  return <Component animation={animation}>{children}</Component>;
};
