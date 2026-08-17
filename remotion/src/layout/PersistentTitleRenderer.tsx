import React from 'react';
import {interpolate, useCurrentFrame} from 'remotion';
import {TextBlockRenderer} from './TextBlockRenderer';

export const PersistentTitleRenderer: React.FC<{title?: any | null; settled?: boolean}> = ({title, settled = false}) => {
  const frame = useCurrentFrame();
  if (!title) return null;
  const opacity = settled ? 1 : interpolate(frame, [0, Math.max(1, title.entrance_duration_frames - 1)], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const block = {...title, block_id: 'persistent-title'};
  return <div data-persistent-title style={{position: 'absolute', inset: 0, opacity, zIndex: title.z_index, pointerEvents: 'none'}}>
    <TextBlockRenderer block={block} content={title.content}/>
  </div>;
};
