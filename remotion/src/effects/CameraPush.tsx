import React from 'react';
import {interpolate, useCurrentFrame} from 'remotion';
import type {EffectProps} from './types';

export const CameraPush: React.FC<EffectProps> = ({animation, children}) => {
  const frame = useCurrentFrame();
  const duration = Math.max(1, animation?.duration_frames ?? 18);
  if (frame >= duration) return <>{children}</>;
  const amount = Number(animation?.params.translatePercent ?? 4);
  const translateX = interpolate(frame, [0, duration], [amount, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  // The stationary layer guarantees that the contained image remains fully
  // visible. Only a transient duplicate translates to create the push cue.
  return <div style={{position: 'absolute', inset: 0}}>{children}<div style={{position: 'absolute', inset: 0, transform: `translateX(${translateX}%)`, opacity: 0.2, pointerEvents: 'none'}}>{children}</div></div>;
};
