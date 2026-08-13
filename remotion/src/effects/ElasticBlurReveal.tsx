import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import type {EffectProps} from './types';

export const ElasticBlurReveal: React.FC<EffectProps> = ({animation, children}) => {
  const frame = useCurrentFrame();
  const elapsed = frame - (animation?.start_frame ?? 0);
  const {fps} = useVideoConfig();
  const duration = Math.max(1, animation?.duration_frames ?? 24);
  if (elapsed < 0 || elapsed >= duration) return <>{children}</>;

  const intensity = Math.min(1, Math.max(0, Number(animation?.params.intensity ?? 0.65)));
  const blurPx = Math.min(24, Math.max(0, Number(animation?.params.blur_px ?? 7)));
  const startOpacity = Math.min(1, Math.max(0, Number(animation?.params.opacity ?? 0.82)));
  const progress = spring({frame: elapsed, fps, config: {damping: 13, stiffness: 165, mass: 0.75}, durationInFrames: duration});
  const scaleX = interpolate(progress, [0, 1], [1 + intensity * 0.2, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const scaleY = interpolate(progress, [0, 1], [1 - intensity * 0.13, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const opacity = interpolate(progress, [0, 1], [startOpacity, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const blur = interpolate(progress, [0, 1], [blurPx, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  return <div style={{position: 'absolute', inset: 0, transform: `scaleX(${scaleX}) scaleY(${scaleY})`, opacity, filter: `blur(${blur}px)`, transformOrigin: 'center'}}>{children}</div>;
};
