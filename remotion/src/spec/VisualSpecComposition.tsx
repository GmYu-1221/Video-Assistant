import React from 'react';
import {AbsoluteFill, Img, useCurrentFrame} from 'remotion';
import type {RemotionPropsWithVisualSpec, VisualSpecLayer, VisualSpecScene, VisualSpecTrack} from '../types';
import {trackValue} from './TrackEvaluator';

const Layer: React.FC<{layer: VisualSpecLayer; region: {x: number; y: number; width: number; height: number; overflow?: 'visible'|'hidden'}; frame: number; props: RemotionPropsWithVisualSpec; transitionTracks?: VisualSpecTrack[]}> = ({layer, region, frame, props, transitionTracks}) => {
  const style = layer.style ?? {};
  const tracks = [...(layer.tracks ?? []), ...(transitionTracks ?? [])];
  const opacity = trackValue(tracks, 'opacity', frame, 1);
  const scale = trackValue(tracks, 'transform.scale', frame, 1);
  const x = trackValue(tracks, 'transform.translateX', frame, 0);
  const y = trackValue(tracks, 'transform.translateY', frame, 0);
  const blur = trackValue(tracks, 'filter.blur', frame, 0);
  const common: React.CSSProperties = {position: 'absolute', left: region.x, top: region.y, width: region.width, height: region.height, opacity, transform: `translate(${x}%, ${y}%) scale(${scale})`, transformOrigin: String(style.transform_origin ?? 'center center'), filter: blur ? `blur(${blur}px)` : undefined, overflow: region.overflow ?? 'visible'};
  if (layer.type === 'text') return <div style={{...common, color: String(style.color ?? '#fff'), fontSize: Number(style.font_size ?? 36), lineHeight: Number(style.line_height ?? 1.3), textAlign: (style.align as React.CSSProperties['textAlign']) ?? 'center', whiteSpace: 'pre-wrap', fontWeight: Number(style.font_weight ?? 400)}}>{layer.source?.content ?? ''}</div>;
  if (layer.type === 'solid' || layer.type === 'overlay') return <div style={{...common, background: String(style.background ?? '#fff')}} />;
  const asset = props.images.find((candidate) => candidate.id === layer.source?.asset_id);
  if (!asset) return null;
  return <div style={{...common, background: String(style.background ?? '#000')}}><Img src={`${props.media_base_url ?? ''}/${asset.relative_path}`} style={{width: '100%', height: '100%', objectFit: 'contain'}} /></div>;
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
    {transition?.tracks?.map((track: VisualSpecTrack, index) => track.target === 'transition-overlay' ? <div key={`overlay-${index}`} style={{position: 'absolute', inset: 0, background: String(transition.params?.flash_color ?? '#fff'), opacity: trackValue([track], 'overlay.opacity', frame - transition.start_frame, 0), pointerEvents: 'none'}} /> : null)}
  </AbsoluteFill>;
};
