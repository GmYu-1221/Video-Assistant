import {AbsoluteFill} from 'remotion';
import {presentation} from './types';
export const glitch = () => presentation(({children, presentationProgress, presentationDirection}) => {
  const decay = 1-presentationProgress; const offset = Math.sin(presentationProgress*47)*decay*9;
  return <AbsoluteFill style={{opacity:presentationDirection === 'entering' ? Math.min(1,presentationProgress*1.7) : 1}}><AbsoluteFill style={{transform:`translateX(${offset}px)`,mixBlendMode:'screen',opacity:decay*.45,filter:'sepia(1) saturate(6) hue-rotate(315deg)'}}>{children}</AbsoluteFill><AbsoluteFill style={{transform:`translateX(${-offset}px)`,mixBlendMode:'screen',opacity:decay*.35,filter:'sepia(1) saturate(7) hue-rotate(165deg)'}}>{children}</AbsoluteFill><AbsoluteFill style={{clipPath:`inset(${35+Math.sin(presentationProgress*31)*20}% 0 ${35-Math.sin(presentationProgress*31)*20}% 0)`,transform:`translateX(${offset*1.4}px)`}}>{children}</AbsoluteFill><AbsoluteFill>{children}</AbsoluteFill></AbsoluteFill>;
});
