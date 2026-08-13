import React from 'react';
import {Composition} from 'remotion';
import {Slideshow} from './Composition';
import {RemotionProps, RemotionPropsWithVisualSpec} from './types';
import {VisualSpecComposition} from './spec/VisualSpecComposition';
export const Root: React.FC = () => <>
  <Composition id="Slideshow" component={Slideshow} width={1920} height={1080} fps={30} durationInFrames={150} defaultProps={{} as RemotionProps} calculateMetadata={({props}: {props: RemotionProps}) => ({width:props.width,height:props.height,fps:props.fps,durationInFrames:Math.max(...(props.timeline ?? []).map((x)=>x.end_frame),1)})}/>
  <Composition id="VisualSpec" component={VisualSpecComposition} width={1080} height={1920} fps={30} durationInFrames={150} defaultProps={{} as RemotionPropsWithVisualSpec} calculateMetadata={({props}: {props: RemotionPropsWithVisualSpec}) => ({width:props.visual_spec?.composition.width ?? props.width,height:props.visual_spec?.composition.height ?? props.height,fps:props.visual_spec?.composition.fps ?? props.fps,durationInFrames:props.visual_spec?.composition.duration_frames ?? 1})}/>
</>;
