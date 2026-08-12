import React from 'react';
import {interpolate, useCurrentFrame} from 'remotion';
import type {EffectProps} from './types';

export const LightLeak: React.FC<EffectProps> = ({animation, children}) => {
  const frame = useCurrentFrame();
  const duration = Math.max(1, animation?.duration_frames ?? 5);
  if (frame >= duration) return <>{children}</>;
  const progress = interpolate(frame, [0, duration], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const intensity = Number(animation?.params.intensity ?? 0.75);
  return <div style={{position: 'absolute', inset: 0}}>{children}<div style={{position: 'absolute', inset: 0, pointerEvents: 'none', background: 'radial-gradient(circle at 20% 55%, rgba(255,170,60,0.9), transparent 64%)', mixBlendMode: 'screen', opacity: Math.sin(progress * Math.PI) * intensity}} /></div>;
};
