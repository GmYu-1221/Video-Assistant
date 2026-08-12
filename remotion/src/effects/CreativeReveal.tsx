import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import type {EffectProps} from './types';

export const CreativeReveal: React.FC<EffectProps> = ({animation, children}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const duration = Math.max(1, animation?.duration_frames ?? 18);
  const params = animation?.params ?? {};
  if (frame >= duration) return <>{children}</>;
  const progress = spring({frame, fps, config: {damping: 18, stiffness: 140}, durationInFrames: duration});
  const energy = Math.min(1, Math.max(0, Number(params.energy ?? 0.5)));
  const translateY = params.direction === 'up'
    ? interpolate(progress, [0, 1], [20 + energy * 20, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})
    : 0;
  const opacity = interpolate(progress, [0, 1], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const blur = interpolate(progress, [0, 1], [Number(params.blurPx ?? 10), 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const maskSize = interpolate(progress, [0, 1], [0, 160], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return <div style={{position: 'absolute', inset: 0, opacity, translate: `0 ${translateY}%`, filter: `blur(${blur}px)`, maskImage: params.mask === false ? undefined : `radial-gradient(circle, black ${maskSize}%, transparent ${maskSize + 20}%)`, WebkitMaskImage: params.mask === false ? undefined : `radial-gradient(circle, black ${maskSize}%, transparent ${maskSize + 20}%)`}}>{children}</div>;
};
