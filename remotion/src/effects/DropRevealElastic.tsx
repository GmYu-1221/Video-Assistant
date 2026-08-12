import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import type {EffectProps} from './types';

export const DropRevealElastic: React.FC<EffectProps> = ({animation, children}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const duration = Math.max(1, animation?.duration_frames ?? 20);
  if (frame >= duration) return <>{children}</>;
  const progress = spring({frame, fps, config: {damping: 12, stiffness: 150}, durationInFrames: duration});
  const y = interpolate(progress, [0, 1], [-110, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const scaleY = interpolate(progress, [0, 0.82, 1], [1.18, 0.9, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const blur = interpolate(progress, [0, 1], [12, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return <div style={{position: 'absolute', inset: 0, transform: `translateY(${y}%) scaleY(${scaleY})`, filter: `blur(${blur}px)`, transformOrigin: 'center bottom'}}>{children}</div>;
};
