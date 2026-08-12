import React from 'react';
import {interpolate, useCurrentFrame} from 'remotion';
import type {EffectProps} from './types';

export const CardFlipReveal: React.FC<EffectProps> = ({animation, children}) => {
  const frame = useCurrentFrame();
  const duration = Math.max(1, animation?.duration_frames ?? 18);
  // Return the unwrapped scene once the entrance has settled. This leaves no
  // persistent transform on ImageFrame's contain layout.
  if (frame >= duration) return <>{children}</>;
  const rotateY = interpolate(frame, [0, duration], [180, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const perspective = Number(animation?.props.perspective ?? 800);
  // Showing the reverse face avoids exposing the composition background while
  // the card is at 180 degrees. ImageFrame still owns the contain geometry.
  return <div style={{position: 'absolute', inset: 0, perspective}}><div style={{position: 'absolute', inset: 0, transform: `rotateY(${rotateY}deg)`, transformStyle: 'preserve-3d', backfaceVisibility: 'visible'}}>{children}</div></div>;
};
