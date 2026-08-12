import React from 'react';
import {Easing, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';

type EntranceConfig = {type?: string; durationInFrames?: number};
type ImageFrameProps = {src: string; motion?: string; entrance?: EntranceConfig};

export const ImageFrame: React.FC<ImageFrameProps> = ({src, motion = 'static', entrance}) => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  const entranceType = entrance?.type ?? 'fade_scale';
  const entranceDuration = Math.max(1, entrance?.durationInFrames ?? 15);
  const entranceProgress = interpolate(frame, [0, entranceDuration], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.inOut(Easing.quad),
  });
  let opacity = entranceType === 'none' ? 1 : entranceProgress;
  let entranceScale = entranceType === 'fade_scale' ? 0.96 + 0.04 * entranceProgress : 1;
  let entranceY = entranceType === 'slide_up' ? 4 * (1 - entranceProgress) : 0;
  let scale = entranceScale;
  let x = 0;
  let y = entranceY;

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

  const transform = motion === 'static' && entranceType === 'fade' ? 'none' : `translate(${x}%, ${y}%) scale(${scale})`;
  return <img src={src} style={{width: '100%', height: '100%', objectFit: 'cover', transform, opacity}} />;
};
