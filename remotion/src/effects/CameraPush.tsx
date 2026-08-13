import React from 'react';
import {interpolate, useCurrentFrame} from 'remotion';
import type {EffectProps} from './types';

export const CameraPush: React.FC<EffectProps> = ({animation, children}) => {
  const frame = useCurrentFrame();
  const elapsed = frame - (animation?.start_frame ?? 0);
  const duration = Math.max(1, animation?.duration_frames ?? 18);
  if (elapsed >= duration) return <>{children}</>;
  const amount = Number(animation?.params.translatePercent ?? 4);
  const translateX = interpolate(elapsed, [0, duration], [amount, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const motionBlur = animation?.params.motion_blur === true;
  const blur = motionBlur ? Math.abs(translateX) * 0.35 : 0;
  return <div style={{position: 'absolute', inset: 0, transform: `translateX(${translateX}%)`, filter: blur ? `blur(${blur}px)` : undefined}}>{children}</div>;
};
