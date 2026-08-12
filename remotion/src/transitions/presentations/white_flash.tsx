import {AbsoluteFill} from 'remotion';
import {presentation} from './types';
export const whiteFlash = () => presentation(({children, presentationProgress, presentationDirection}) => <AbsoluteFill><AbsoluteFill style={{opacity: presentationDirection === 'entering' ? presentationProgress : 1}}>{children}</AbsoluteFill><AbsoluteFill style={{backgroundColor:'#fff',opacity: Math.sin(presentationProgress * Math.PI)}} /></AbsoluteFill>);
