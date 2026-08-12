import React from 'react';
import {AbsoluteFill} from 'remotion';
import {TransitionSeries} from '@remotion/transitions';
import {RemotionProps} from './types';
import {ImageFrame} from './components/ImageFrame';
import {AudioTrack} from './components/AudioTrack';
import {TransitionFactory} from './transitions';

export const Slideshow: React.FC<RemotionProps> = (props) => {
  const base = props.media_base_url ?? '';
  const map = new Map(props.images.map((x) => [x.id, x]));
  return <AbsoluteFill style={{backgroundColor: 'black'}}>
    <TransitionSeries>
      {props.timeline.flatMap((item, index) => {
        const asset = map.get(item.asset_id);
        const isLast = index === props.timeline.length - 1;
        const transitionFrames = isLast ? 0 : item.transition.duration_frames;
        const sequence = <TransitionSeries.Sequence key={`sequence-${item.asset_id}`} durationInFrames={item.duration_frames + transitionFrames}>
          <ImageFrame src={`${base}/${asset?.relative_path ?? ''}`} motion={asset?.motion ?? 'static'} entrance={asset?.entrance} />
        </TransitionSeries.Sequence>;
        if (isLast) return [sequence];
        return [sequence, TransitionFactory(item.transition, `transition-${item.asset_id}`)];
      })}
    </TransitionSeries>
    <AudioTrack src={`${base}/${props.audio.path}`} />
  </AbsoluteFill>;
};
