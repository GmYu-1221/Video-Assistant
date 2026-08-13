import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import type {EffectProps} from './types';

export const ParticleFlipReveal: React.FC<EffectProps> = ({animation, children}) => {
  const frame = useCurrentFrame();
  const elapsed = frame - (animation?.start_frame ?? 0);
  const {fps} = useVideoConfig();
  const duration = Math.max(1, animation?.duration_frames ?? 20);
  const params = animation?.params ?? {};
  if (elapsed >= duration) return <>{children}</>;
  const progress = spring({frame: elapsed, fps, config: {damping: 16, stiffness: 145}, durationInFrames: duration});
  const axis = params.rotation_axis === 'X' ? 'X' : 'Y';
  const rotation = interpolate(progress, [0, 1], [150, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const blur = interpolate(progress, [0, 1], [params.motion_blur === false ? 0 : 10, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const particleVeil = interpolate(progress, [0, 0.75, 1], [1, 0.25, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const density = Math.max(24, Number(params.particle_density ?? 120));
  const spacing = Math.max(4, Math.round(192 / Math.sqrt(density)));
  return <div style={{position: 'absolute', inset: 0, perspective: Number(params.perspective ?? 800)}}><div style={{position: 'absolute', inset: 0, transform: `rotate${axis}(${rotation}deg)`, filter: `blur(${blur}px)`, transformStyle: 'preserve-3d'}}>{children}</div><div style={{position: 'absolute', inset: 0, pointerEvents: 'none', opacity: particleVeil, backgroundImage: 'radial-gradient(circle, rgba(255,255,255,.8) 0 1px, transparent 1.5px)', backgroundSize: `${spacing}px ${spacing}px`, mixBlendMode: 'screen'}} /></div>;
};
