import {AbsoluteFill, interpolate} from 'remotion';
import type {TransitionPresentationComponentProps} from '@remotion/transitions';

export type ShakeTransitionProps = {intensity?: number; motion_blur?: boolean};

export const ShakeTransition: React.FC<TransitionPresentationComponentProps<ShakeTransitionProps>> = ({children, presentationDirection, presentationProgress, passedProps}) => {
  const intensity = Math.max(0, Math.min(1, passedProps.intensity ?? .7));
  const decay = presentationDirection === 'exiting' ? 1 - presentationProgress : presentationProgress;
  const offset = Math.sin(presentationProgress * 54) * intensity * decay * 22;
  const opacity = presentationDirection === 'exiting'
    ? interpolate(presentationProgress, [0, 1], [1, 0], {extrapolateRight: 'clamp'})
    : interpolate(presentationProgress, [0, .4, 1], [0, .8, 1], {extrapolateRight: 'clamp'});
  return <AbsoluteFill style={{opacity, transform: `translate(${offset}px, ${-offset * .35}px)`, filter: passedProps.motion_blur ? `blur(${decay * intensity * 2}px)` : undefined}}>{children}</AbsoluteFill>;
};
