import React from 'react';
import {AbsoluteFill} from 'remotion';
import {TransitionSeries} from '@remotion/transitions';
import {RemotionProps, TransitionEffectPlan} from './types';
import {ImageFrame} from './components/ImageFrame';
import {AudioTrack} from './components/AudioTrack';
import {TransitionFactory} from './transitions';
import {TransitionEffectRenderer} from './transitions/TransitionEffectRenderer';
import {EffectRenderer} from './effects';
import {VisualEffectRenderer} from './visual/VisualEffectRenderer';
import {BackgroundVideoLayer} from './components/BackgroundVideoLayer';

export const Slideshow: React.FC<RemotionProps> = (props) => {
  const base = props.media_base_url ?? '';
  const map = new Map(props.images.map((x) => [x.id, x]));
  return <AbsoluteFill style={{backgroundColor: props.background_video ? 'transparent' : 'black'}}>
    <BackgroundVideoLayer config={props.background_video} mediaBaseUrl={props.media_base_url}/>
    <TransitionSeries>
      {props.timeline.flatMap((item, index) => {
        const asset = map.get(item.asset_id);
        const isLast = index === props.timeline.length - 1;
        const priority = {transition: 0, entrance: 1, effect: 2, exit: 3, camera: 4};
        const events = [...(item.visual_events ?? [])].sort((a, b) => priority[a.phase] - priority[b.phase] || a.start_frame - b.start_frame);
        const transitionEvent = events.find((event) => event.phase === 'transition');
        const transitionFrames = isLast ? 0 : transitionEvent?.duration_frames ?? item.transition_effect?.duration_frames ?? item.transition.duration_frames;
        const incomingTransition = props.timeline[index - 1]?.visual_events?.find((event) => event.phase === 'transition' && event.target_asset_id === item.asset_id);
        // The incoming transition already controls this scene's reveal during
        // the overlap, so an entrance wrapper would create a competing reveal.
        const sceneEvents = events.filter((event) => event.phase !== 'transition' && !(incomingTransition && event.phase === 'entrance'));
        const sceneContent = sceneEvents.reduce<React.ReactNode>((content, event, eventIndex) => VisualEffectRenderer(event, `visual-${item.asset_id}-${eventIndex}`, content), <ImageFrame src={`${base}/${asset?.relative_path ?? ''}`} imageWidth={asset?.width ?? props.width} imageHeight={asset?.height ?? props.height} motion={asset?.motion ?? 'static'} entrance={incomingTransition ? undefined : asset?.entrance} backgroundColor={props.background_video ? 'transparent' : undefined} />);
        const sequence = <TransitionSeries.Sequence key={`sequence-${item.asset_id}`} durationInFrames={item.duration_frames + transitionFrames}>
          {events.length ? sceneContent : <EffectRenderer animation={item.animation}><ImageFrame src={`${base}/${asset?.relative_path ?? ''}`} imageWidth={asset?.width ?? props.width} imageHeight={asset?.height ?? props.height} motion={asset?.motion ?? 'static'} entrance={asset?.entrance} backgroundColor={props.background_video ? 'transparent' : undefined} /></EffectRenderer>}
        </TransitionSeries.Sequence>;
        if (isLast) return [sequence];
        const nextItem = props.timeline[index + 1];
        const safeTransition = {
          ...item.transition,
          duration_frames: Math.min(item.transition.duration_frames, item.duration_frames, nextItem.duration_frames),
          background_color: asset?.backgroundColor,
        };
        const safeTransitionEffect = transitionEvent && ['card_flip_transition', 'glass_shatter_transition', 'shake_transition', 'gaussian_blur_transition', 'directional_blur_transition', 'pixel_blur_transition', 'bokeh_blur_transition', 'water_ripple_transition', 'zoom_through_transition'].includes(transitionEvent.type) ? {
          from_asset_id: item.asset_id,
          to_asset_id: transitionEvent.target_asset_id ?? nextItem.asset_id,
          type: transitionEvent.type,
          duration_frames: transitionEvent.duration_frames,
          params: transitionEvent.params,
        } : item.transition_effect && {
          ...item.transition_effect,
          duration_frames: Math.min(item.transition_effect.duration_frames, item.duration_frames, nextItem.duration_frames),
        };
        return [sequence, safeTransitionEffect
          ? TransitionEffectRenderer(safeTransitionEffect as TransitionEffectPlan, `transition-effect-${item.asset_id}`)
          : TransitionFactory(safeTransition, `transition-${item.asset_id}`)];
      })}
    </TransitionSeries>
    <AudioTrack src={`${base}/${props.audio.path}`} />
  </AbsoluteFill>;
};
