import {AbsoluteFill} from 'remotion';
import {presentation} from './types';
export const pixelReveal = () => presentation(({children, presentationProgress, presentationDirection}) => {
  const p = presentationDirection === 'entering' ? presentationProgress : 1-presentationProgress;
  return <AbsoluteFill>{children}<AbsoluteFill style={{pointerEvents:'none',opacity:1-p,backgroundImage:'linear-gradient(90deg,#000 50%,transparent 50%),linear-gradient(#000 50%,transparent 50%)',backgroundSize:'32px 32px',mixBlendMode:'multiply'}}/></AbsoluteFill>;
});
