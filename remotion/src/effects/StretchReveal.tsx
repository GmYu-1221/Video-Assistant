import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import type {EffectProps} from './types';

export const StretchReveal: React.FC<EffectProps> = ({animation, children}) => {
  const frame = useCurrentFrame();
  const elapsed = frame - (animation?.start_frame ?? 0);
  const {fps} = useVideoConfig();
  const duration = Math.max(1, animation?.duration_frames ?? 18);
  if (elapsed >= duration) return <>{children}</>;
  const progress = spring({frame: elapsed, fps, config: {damping: 18, stiffness: 140}, durationInFrames: duration});
  const strength = Number(animation?.params.strength ?? 0.8);
  const stretch = 1 + strength * (1 - progress);
  const y = interpolate(progress, [0, 1], [8, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const blur = interpolate(progress, [0, 1], [Number(animation?.params.blurPx ?? 12), 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return <div style={{position: 'absolute', inset: 0, transform: `translateY(${y}%) scale(${stretch})`, filter: `blur(${blur}px)`, transformOrigin: 'center bottom'}}>{children}</div>;
};
