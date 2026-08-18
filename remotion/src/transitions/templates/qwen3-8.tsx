import React from 'react';
import {AbsoluteFill} from 'remotion';
import type {TemplatePresentationComponent} from './types';
import {getQwen38TransitionState} from './qwen3-8-state';

export const Qwen38Transition: TemplatePresentationComponent = ({
  children,
  presentationDirection,
  presentationProgress,
  parameters,
}) => {
  if (presentationDirection === 'exiting') {
    return <AbsoluteFill>{children}</AbsoluteFill>;
  }

  const state = getQwen38TransitionState(presentationProgress, parameters);
  return (
    <AbsoluteFill
      style={{
        opacity: state.opacity,
        translate: state.translateYPct === 0 ? 'none' : `0 ${state.translateYPct}%`,
        filter: state.blurPx === 0 ? 'none' : `blur(${state.blurPx}px)`,
      }}
    >
      {children}
    </AbsoluteFill>
  );
};
