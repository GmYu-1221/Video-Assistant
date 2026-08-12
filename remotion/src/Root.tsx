import React from 'react';
import {Composition} from 'remotion';
import {Slideshow} from './Composition';
import {RemotionProps} from './types';
export const Root: React.FC = () => <Composition id="Slideshow" component={Slideshow} width={1920} height={1080} fps={30} durationInFrames={150} defaultProps={{} as RemotionProps} calculateMetadata={({props}: {props: RemotionProps}) => ({width:props.width,height:props.height,fps:props.fps,durationInFrames:Math.max(...(props.timeline ?? []).map((x)=>x.end_frame),1)})}/>;
