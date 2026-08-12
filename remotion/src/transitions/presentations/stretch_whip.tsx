import {AbsoluteFill} from 'remotion';
import {presentation} from './types';

export const stretchWhip = () => presentation(({children, presentationProgress, presentationDirection}) => {
  const eased = Math.sin(presentationProgress * Math.PI);
  const entering = presentationDirection === 'entering';
  const scaleX = entering ? 0.6 + presentationProgress * 0.4 : 1 + eased * 0.35;
  const translateX = entering ? (1 - presentationProgress) * 100 : -presentationProgress * 100;
  const blur = eased * 15;

  // At progress=1 all values are exactly neutral, so the next static ImageFrame
  // resumes its contain layout with no transform or filter.
  if (presentationProgress >= 1) return <AbsoluteFill>{children}</AbsoluteFill>;
  return <AbsoluteFill style={{transform: `translateX(${translateX}%) scaleX(${scaleX})`, filter: `blur(${blur}px)`, transformOrigin: entering ? 'left center' : 'right center'}}>{children}</AbsoluteFill>;
});
