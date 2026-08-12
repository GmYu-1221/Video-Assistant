import {AbsoluteFill} from 'remotion';
import {presentation} from './types';
export const lightLeak = () => presentation(({children, presentationProgress, presentationDirection}) => <AbsoluteFill><AbsoluteFill style={{opacity:presentationDirection === 'entering' ? presentationProgress : 1}}>{children}</AbsoluteFill><AbsoluteFill style={{background:'radial-gradient(circle at 20% 50%, rgba(255,170,60,.9), transparent 65%)',mixBlendMode:'screen',opacity:Math.sin(presentationProgress * Math.PI) * .8}} /></AbsoluteFill>);
