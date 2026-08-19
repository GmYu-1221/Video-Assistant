import React from 'react';
import {AbsoluteFill} from 'remotion';
import type {TemplatePresentationComponent} from './types';
import {getZoomWhipV2State} from './zoom-whip-v2-state';

export const ZoomWhipV2Transition: TemplatePresentationComponent = ({
  children,
  presentationDirection,
  presentationProgress,
  parameters,
}) => {
  const state = getZoomWhipV2State(presentationProgress, presentationDirection, parameters);
  return (
    <AbsoluteFill
      style={{
        opacity: state.opacity,
        transform: `translateX(${state.translateXPct}%) scale(${state.scale})`,
        filter: state.blurPx === 0 ? 'none' : `blur(${state.blurPx}px)`,
        transformOrigin: 'center center',
      }}
    >
      {children}
    </AbsoluteFill>
  );
};
