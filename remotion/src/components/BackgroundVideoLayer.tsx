import React from 'react';
import {Video} from '@remotion/media';
import {AbsoluteFill} from 'remotion';
import type {BackgroundVideoConfig} from '../types';

export const BackgroundVideoLayer: React.FC<{
  config?: BackgroundVideoConfig | null;
  mediaBaseUrl?: string;
  tintColor?: string;
}> = ({config, mediaBaseUrl, tintColor = '#101214'}) => {
  if (!config) return null;
  return <AbsoluteFill style={{zIndex: 0, overflow: 'hidden', backgroundColor: tintColor}}>
    <Video
      src={`${mediaBaseUrl ?? ''}/${config.path}`}
      loop={config.loop}
      muted={config.muted}
      volume={0}
      objectFit="cover"
      style={{width: '100%', height: '100%'}}
    />
    <AbsoluteFill style={{backgroundColor: tintColor, opacity: config.overlay_opacity, pointerEvents: 'none'}} />
  </AbsoluteFill>;
};
