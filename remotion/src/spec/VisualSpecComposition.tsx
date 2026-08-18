import React from 'react';
import {AbsoluteFill, Img, interpolate, useCurrentFrame} from 'remotion';
import type {RemotionPropsWithVisualSpec, VisualSpecLayer, VisualSpecScene, VisualSpecTrack} from '../types';
import {trackValue} from './TrackEvaluator';
import {AudioTrack} from '../components/AudioTrack';
import {SceneLayoutRenderer} from '../layout/SceneLayoutRenderer';
import {PersistentTitleRenderer} from '../layout/PersistentTitleRenderer';
import {BackgroundVideoLayer} from '../components/BackgroundVideoLayer';

const Layer: React.FC<{layer: VisualSpecLayer; region: {x: number; y: number; width: number; height: number; overflow?: 'visible'|'hidden'}; frame: number; props: RemotionPropsWithVisualSpec; transitionTracks?: VisualSpecTrack[]}> = ({layer, region, frame, props, transitionTracks}) => {
  const style = layer.style ?? {};
  // Transition tracks take ownership during their overlap. Scene hold tracks
  // resume only after the transition, avoiding a competing scale value.
  const tracks = transitionTracks?.length ? transitionTracks : (layer.tracks ?? []);
  const opacity = trackValue(tracks, 'opacity', frame, 1);
  const scale = trackValue(tracks, 'transform.scale', frame, 1);
  const scaleY = trackValue(tracks, 'transform.scaleY', frame, 1);
  const x = trackValue(tracks, 'transform.translateX', frame, 0);
  const y = trackValue(tracks, 'transform.translateY', frame, 0);
  const blur = trackValue(tracks, 'filter.blur', frame, 0);
  const frameStyle: React.CSSProperties = {position: 'absolute', left: region.x, top: region.y + (layer.text_style?.top_offset ?? 0), width: region.width, height: region.height, overflow: region.overflow ?? 'visible'};
  const transformStyle: React.CSSProperties = {width: '100%', height: '100%', opacity, transform: `translate(${x}%, ${y}%) scale(${scale}, ${scaleY})`, transformOrigin: String(style.transform_origin ?? 'center center'), filter: blur ? `blur(${blur}px)` : undefined};
  if (layer.type === 'text') {
    const text = layer.text_style!;
    return <div style={{...frameStyle, ...transformStyle, color: text.color, fontSize: text.font_size, lineHeight: text.line_height, textAlign: text.align ?? 'center', whiteSpace: 'pre-wrap', fontWeight: text.font_weight ?? 400, overflow: 'hidden', display: '-webkit-box', WebkitBoxOrient: 'vertical', WebkitLineClamp: text.max_lines}}>{layer.source?.content ?? ''}</div>;
  }
  if (layer.type === 'solid' || layer.type === 'overlay') return <div style={{...frameStyle, ...transformStyle, background: String(style.background ?? '#fff')}} />;
  const asset = props.images.find((candidate) => candidate.id === layer.source?.asset_id);
  if (!asset) return null;
  return <div style={frameStyle}><div style={{...transformStyle, background: String(style.background ?? (props.background_video ? 'transparent' : '#000'))}}><Img src={`${props.media_base_url ?? ''}/${asset.relative_path}`} style={{width: '100%', height: '100%', objectFit: style.object_fit === 'cover' ? 'cover' : 'contain', objectPosition: String(style.object_position ?? 'center')}} /></div></div>;
};

const Scene: React.FC<{scene: VisualSpecScene; frame: number; props: RemotionPropsWithVisualSpec; transitionTracks?: VisualSpecTrack[]; trackFrame?: number}> = ({scene, frame, props, transitionTracks, trackFrame}) => <>{scene.layers.map((layer) => { const region = props.visual_spec!.layout.regions[layer.region]; const tracks = transitionTracks?.filter((track) => track.target === layer.id); return region ? <Layer key={layer.id} layer={layer} region={region} frame={trackFrame ?? frame - scene.start_frame} props={props} transitionTracks={tracks} /> : null; })}</>;

export const VisualSpecComposition: React.FC<RemotionPropsWithVisualSpec> = (props) => {
  const frame = useCurrentFrame();
  const spec = props.visual_spec!;
  const scene = spec.scenes.find((candidate) => frame >= candidate.start_frame && frame < candidate.start_frame + candidate.duration_frames) ?? spec.scenes[spec.scenes.length - 1];
  const transition = spec.transitions?.find((candidate) => frame >= candidate.start_frame && frame < candidate.start_frame + candidate.duration_frames);
  const incomingScene = transition ? spec.scenes.find((candidate) => candidate.id === transition.to_scene) : undefined;
  const timelineItem = props.timeline.find((item) => frame >= item.start_frame && frame < item.end_frame);
  if (timelineItem?.layout && timelineItem.narrative && timelineItem.resolved_state) {
    const localFrame = frame - timelineItem.start_frame;
    const boundary = timelineItem.resolved_state.boundary_action;
    const previous = props.timeline[Math.max(0, props.timeline.indexOf(timelineItem) - 1)];
    const transitionFrames = Math.min(9, timelineItem.duration_frames);
    const mediaChanged = previous?.resolved_state?.resolved_media_id !== timelineItem.resolved_state.resolved_media_id;
    const transitionActive = mediaChanged && (boundary === 'accent' || boundary === 'scene_cut') && localFrame < transitionFrames;
    const progress = interpolate(localFrame, [0, Math.max(1, transitionFrames - 2)], [0, 1], {extrapolateLeft:'clamp',extrapolateRight:'clamp'});
    const flash = interpolate(localFrame, [0, 2, transitionFrames - 1], [0, boundary === 'scene_cut' ? .75 : .95, 0], {extrapolateLeft:'clamp',extrapolateRight:'clamp'});
    const incomingMediaStyle: React.CSSProperties = transitionActive ? {opacity: .35 + progress * .65, filter: `blur(${(1 - progress) * (boundary === 'scene_cut' ? 28 : 24)}px)`, transform: boundary === 'scene_cut' ? `scale(1.06, ${1 + (1 - progress) * .12})` : `scale(${1 + (1 - progress) * .12})`, transformOrigin:'center'} : {};
    return <AbsoluteFill style={{background: props.background_video ? 'transparent' : '#000'}}>
      <BackgroundVideoLayer config={props.background_video} mediaBaseUrl={props.media_base_url} tintColor={(timelineItem.layout as any).background?.color ?? '#101214'}/>
      <SceneLayoutRenderer layout={timelineItem.layout} narrative={timelineItem.narrative} images={props.images} mediaBaseUrl={props.media_base_url} copyVisible={timelineItem.resolved_state.visibility !== 'hidden'} showMedia={!transitionActive} transparentBackground={Boolean(props.background_video)}/>
      {transitionActive && previous?.layout && previous.narrative && <SceneLayoutRenderer layout={previous.layout} narrative={previous.narrative} images={props.images} mediaBaseUrl={props.media_base_url} copyVisible={false} showText={false} mediaStyle={{opacity:1-progress}} transparentBackground/>}
      {transitionActive && <SceneLayoutRenderer layout={timelineItem.layout} narrative={timelineItem.narrative} images={props.images} mediaBaseUrl={props.media_base_url} copyVisible={false} showText={false} mediaStyle={incomingMediaStyle} transparentBackground/>}
      {transitionActive && <div style={{position:'absolute',left:0,top:655,width:1080,height:610,background:'#fff',opacity:flash,zIndex:10,pointerEvents:'none'}}/>}
      <PersistentTitleRenderer title={props.persistent_title}/>
      <AudioTrack src={`${props.media_base_url ?? ''}/${props.audio.path}`} />
    </AbsoluteFill>;
  }
  return <AbsoluteFill style={{background: props.background_video ? 'transparent' : (spec.composition.background ?? '#000')}}>
    <BackgroundVideoLayer config={props.background_video} mediaBaseUrl={props.media_base_url} tintColor={spec.composition.background ?? '#000'}/>
    {spec.persistent_layers?.map((layer) => { const region = spec.layout.regions[layer.region]; return region ? <Layer key={layer.id} layer={layer} region={region} frame={frame} props={props} /> : null; })}
    <Scene scene={scene} frame={frame} props={props} />
    {incomingScene && <Scene scene={incomingScene} frame={frame} props={props} transitionTracks={transition?.tracks} trackFrame={frame - transition!.start_frame} />}
    {transition?.tracks?.map((track: VisualSpecTrack, index) => {
      if (track.target !== 'transition-overlay') return null;
      const stage = spec.layout.regions.stage;
      return stage ? <div key={`overlay-${index}`} style={{position: 'absolute', left: stage.x, top: stage.y, width: stage.width, height: stage.height, overflow: 'hidden', background: String(transition.params?.flash_color ?? '#fff'), opacity: trackValue([track], 'overlay.opacity', frame - transition.start_frame, 0), pointerEvents: 'none'}} /> : null;
    })}
    <AudioTrack src={`${props.media_base_url ?? ''}/${props.audio.path}`} />
  </AbsoluteFill>;
};
