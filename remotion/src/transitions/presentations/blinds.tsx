import {AbsoluteFill} from 'remotion';
import {presentation} from './types';
export const blinds = () => presentation(({children, presentationProgress, presentationDirection}) => {
  const p = presentationDirection === 'entering' ? presentationProgress : 1 - presentationProgress;
  return <AbsoluteFill>{Array.from({length:8}, (_, index) => {
    const local = Math.max(0, Math.min(1, p * 1.35 - index * .05));
    return <div key={index} style={{position:'absolute',left:0,right:0,top:`${index*12.5}%`,height:'12.5%',overflow:'hidden'}}><AbsoluteFill style={{transform:`translateY(${-index*12.5}%)`,clipPath:`inset(0 0 ${(1-local)*100}% 0)`}}>{children}</AbsoluteFill></div>;
  })}</AbsoluteFill>;
});
