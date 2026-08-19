import React from 'react';
import {AbsoluteFill, Img} from 'remotion';

export const BackgroundImageLayer: React.FC<{
  src?: string;
  tintColor?: string;
  overlayOpacity?: number;
}> = ({src, tintColor = '#07090B', overlayOpacity = 0.58}) => {
  return <AbsoluteFill style={{zIndex: 0, overflow: 'hidden', backgroundColor: tintColor}}>
    {src ? <Img
      src={src}
      style={{
        width: '100%',
        height: '100%',
        objectFit: 'cover',
        objectPosition: 'center',
        opacity: 0.72,
      }}
    /> : null}
    <AbsoluteFill style={{backgroundColor: tintColor, opacity: overlayOpacity, pointerEvents: 'none'}} />
  </AbsoluteFill>;
};
