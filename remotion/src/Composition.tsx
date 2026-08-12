import React from 'react';
import {AbsoluteFill} from 'remotion';
import {TransitionSeries} from '@remotion/transitions';
import {RemotionProps} from './types';
import {ImageFrame} from './components/ImageFrame';
import {AudioTrack} from './components/AudioTrack';
import {TransitionEffectFactory, TransitionFactory} from './transitions';
import {EffectRenderer} from './effects';

export const Slideshow: React.FC<RemotionProps> = (props) => {
  const base = props.media_base_url ?? '';
  const map = new Map(props.images.map((x) => [x.id, x]));
  return <AbsoluteFill style={{backgroundColor: 'black'}}>
    <TransitionSeries>
      {props.timeline.flatMap((item, index) => {
        const asset = map.get(item.asset_id);
        const isLast = index === props.timeline.length - 1;
        const transitionFrames = isLast ? 0 : item.transition_effect?.duration_frames ?? item.transition.duration_frames;
        const sequence = <TransitionSeries.Sequence key={`sequence-${item.asset_id}`} durationInFrames={item.duration_frames + transitionFrames}>
          <EffectRenderer animation={item.animation}><ImageFrame src={`${base}/${asset?.relative_path ?? ''}`} imageWidth={asset?.width ?? props.width} imageHeight={asset?.height ?? props.height} motion={asset?.motion ?? 'static'} entrance={asset?.entrance} /></EffectRenderer>
        </TransitionSeries.Sequence>;
        if (isLast) return [sequence];
        const nextItem = props.timeline[index + 1];
        const safeTransition = {
          ...item.transition,
          duration_frames: Math.min(item.transition.duration_frames, item.duration_frames, nextItem.duration_frames),
          background_color: asset?.backgroundColor,
        };
        return [sequence, item.transition_effect
          ? TransitionEffectFactory(item.transition_effect, `transition-effect-${item.asset_id}`)
          : TransitionFactory(safeTransition, `transition-${item.asset_id}`)];
      })}
    </TransitionSeries>
    <AudioTrack src={`${base}/${props.audio.path}`} />
  </AbsoluteFill>;
};
