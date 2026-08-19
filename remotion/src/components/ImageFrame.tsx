import React from 'react';
import {Easing, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';

type EntranceConfig = {type?: 'none' | 'fade_scale' | 'slide_up'; durationInFrames?: number};
type ImageFrameProps = {src: string; imageWidth: number; imageHeight: number; motion?: string; entrance?: EntranceConfig; backgroundColor?: string};

export const ImageFrame: React.FC<ImageFrameProps> = ({src, imageWidth, imageHeight, motion = 'static', entrance, backgroundColor = '#000000'}) => {
  const frame = useCurrentFrame();
  const {durationInFrames, width: videoWidth, height: videoHeight} = useVideoConfig();
  // Scale to the largest rectangle that fits the canvas. Upscaling small images
  // is intentional: a correctly fitted image leaves black bars on only one axis.
  const fitScale = Math.min(videoWidth / imageWidth, videoHeight / imageHeight);
  // Contain is the invariant: every transformed corner must remain in the canvas.
  // Explicit motion receives a small safety margin; static images use the maximal fit.
  const requestedMotionScale = motion === 'zoom_in' || motion === 'ken_burns' ? 1.14 : motion === 'zoom_out' ? 1.14 : 1;
  const safeScale = fitScale / requestedMotionScale;
  const renderWidth = Math.max(1, Math.round(imageWidth * safeScale));
  const renderHeight = Math.max(1, Math.round(imageHeight * safeScale));
  const entranceType = entrance?.type ?? 'none';
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
    if (motion === 'zoom_in' || motion === 'ken_burns') scale = (1.04 + 0.1 * progress) / requestedMotionScale;
    if (motion === 'zoom_out') scale = (1.14 - 0.1 * progress) / requestedMotionScale;
    // Movement is only allowed inside the letterbox margin created above.
    const horizontalMargin = Math.max(0, (videoWidth - renderWidth * requestedMotionScale) / renderWidth * 50);
    const verticalMargin = Math.max(0, (videoHeight - renderHeight * requestedMotionScale) / renderHeight * 50);
    if (motion === 'pan_left') x = -horizontalMargin * progress;
    if (motion === 'pan_right') x = horizontalMargin * progress;
    if (motion === 'pan_up') y = -verticalMargin * progress;
    if (motion === 'pan_down') y = verticalMargin * progress;
  }

  const transform = motion === 'static' && entranceType === 'none' ? 'none' : `translate(${x}%, ${y}%) scale(${scale})`;
  return <div style={{position: 'absolute', inset: 0, backgroundColor}}>
    <img src={src} style={{position: 'absolute', left: (videoWidth - renderWidth) / 2, top: (videoHeight - renderHeight) / 2, width: renderWidth, height: renderHeight, transform, opacity, transformOrigin: 'center center'}} />
  </div>;
};
