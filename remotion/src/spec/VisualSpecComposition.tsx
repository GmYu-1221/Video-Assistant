import React from 'react';
import {AbsoluteFill, Img, useCurrentFrame} from 'remotion';
import type {RemotionPropsWithVisualSpec, VisualSpecLayer, VisualSpecScene, VisualSpecTrack} from '../types';
import {trackValue} from './TrackEvaluator';
import {AudioTrack} from '../components/AudioTrack';

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
  return <div style={frameStyle}><div style={{...transformStyle, background: String(style.background ?? '#000')}}><Img src={`${props.media_base_url ?? ''}/${asset.relative_path}`} style={{width: '100%', height: '100%', objectFit: style.object_fit === 'cover' ? 'cover' : 'contain', objectPosition: String(style.object_position ?? 'center')}} /></div></div>;
};

const Scene: React.FC<{scene: VisualSpecScene; frame: number; props: RemotionPropsWithVisualSpec; transitionTracks?: VisualSpecTrack[]; trackFrame?: number}> = ({scene, frame, props, transitionTracks, trackFrame}) => <>{scene.layers.map((layer) => { const region = props.visual_spec!.layout.regions[layer.region]; const tracks = transitionTracks?.filter((track) => track.target === layer.id); return region ? <Layer key={layer.id} layer={layer} region={region} frame={trackFrame ?? frame - scene.start_frame} props={props} transitionTracks={tracks} /> : null; })}</>;

export const VisualSpecComposition: React.FC<RemotionPropsWithVisualSpec> = (props) => {
  const frame = useCurrentFrame();
  const spec = props.visual_spec!;
  const scene = spec.scenes.find((candidate) => frame >= candidate.start_frame && frame < candidate.start_frame + candidate.duration_frames) ?? spec.scenes[spec.scenes.length - 1];
  const transition = spec.transitions?.find((candidate) => frame >= candidate.start_frame && frame < candidate.start_frame + candidate.duration_frames);
  const incomingScene = transition ? spec.scenes.find((candidate) => candidate.id === transition.to_scene) : undefined;
  return <AbsoluteFill style={{background: spec.composition.background ?? '#000'}}>
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
