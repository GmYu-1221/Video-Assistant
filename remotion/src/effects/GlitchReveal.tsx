import React from 'react';
import {interpolate, useCurrentFrame} from 'remotion';
import type {EffectProps} from './types';

export const GlitchReveal: React.FC<EffectProps> = ({animation, children}) => {
  const frame = useCurrentFrame();
  const duration = Math.max(1, animation?.duration_frames ?? 5);
  if (frame >= duration) return <>{children}</>;
  const offset = interpolate(frame, [0, duration], [Number(animation?.params.rgbOffset ?? 8), 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const slice = `${30 + (frame % 3) * 12}% 0 ${35 - (frame % 3) * 7}% 0`;
  return <div style={{position: 'absolute', inset: 0}}><div style={{position: 'absolute', inset: 0, transform: `translateX(${offset}px)`, opacity: offset ? 0.35 : 0, filter: 'sepia(1) saturate(6) hue-rotate(315deg)', mixBlendMode: 'screen'}}>{children}</div><div style={{position: 'absolute', inset: 0, transform: `translateX(${-offset}px)`, opacity: offset ? 0.3 : 0, filter: 'sepia(1) saturate(7) hue-rotate(165deg)', mixBlendMode: 'screen'}}>{children}</div><div style={{position: 'absolute', inset: 0, clipPath: `inset(${slice})`, transform: `translateX(${offset}px)`}}>{children}</div><div style={{position: 'absolute', inset: 0}}>{children}</div></div>;
};
