import React from 'react';
import {Easing, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';

type ImageFrameProps = {src: string; motion?: string};

export const ImageFrame: React.FC<ImageFrameProps> = ({src, motion = 'static'}) => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  let scale = 1;
  let x = 0;
  let y = 0;

  if (motion !== 'static') {
    const progress = interpolate(frame, [0, durationInFrames], [0, 1], {
      extrapolateRight: 'clamp',
      easing: Easing.inOut(Easing.quad),
    });
    if (motion === 'zoom_in' || motion === 'ken_burns') scale = 1.04 + 0.1 * progress;
    if (motion === 'zoom_out') scale = 1.14 - 0.1 * progress;
    if (motion === 'pan_left') x = -4 * progress;
    if (motion === 'pan_right') x = 4 * progress;
    if (motion === 'pan_up') y = -4 * progress;
    if (motion === 'pan_down') y = 4 * progress;
  }

  const transform = motion === 'static' ? 'none' : `translate(${x}%, ${y}%) scale(${scale})`;
  return <img src={src} style={{width: '100%', height: '100%', objectFit: 'cover', transform}} />;
};
