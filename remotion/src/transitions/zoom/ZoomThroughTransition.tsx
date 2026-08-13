import {AbsoluteFill, interpolate} from 'remotion';
import type {TransitionPresentationComponentProps} from '@remotion/transitions';

export type ZoomThroughTransitionProps = {
  intensity?: number;
  direction?: 'center' | 'left' | 'right' | 'top' | 'bottom' | 'horizontal' | 'vertical' | 'radial' | 'up' | 'down';
};

const transformOrigins: Record<NonNullable<ZoomThroughTransitionProps['direction']>, string> = {
  center: '50% 50%',
  left: '0% 50%',
  right: '100% 50%',
  top: '50% 0%',
  bottom: '50% 100%',
  horizontal: '50% 50%',
  vertical: '50% 50%',
  radial: '50% 50%',
  up: '50% 50%',
  down: '50% 50%',
};

export const ZoomThroughTransition: React.FC<TransitionPresentationComponentProps<ZoomThroughTransitionProps>> = ({children, presentationDirection, presentationProgress, passedProps}) => {
  const intensity = Math.max(0, Math.min(1, passedProps.intensity ?? 0.75));
  const direction = passedProps.direction ?? 'center';
  const transformOrigin = transformOrigins[direction];
  const exiting = presentationDirection === 'exiting';
  const scale = exiting
    ? interpolate(presentationProgress, [0, 1], [1, 1.45 + intensity * 1.15], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})
    : interpolate(presentationProgress, [0, 1], [1.12 + intensity * 0.18, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const opacity = exiting
    ? interpolate(presentationProgress, [0.62, 1], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})
    : interpolate(presentationProgress, [0, 0.42, 1], [0, 0.88, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  return <AbsoluteFill style={{overflow: 'hidden'}}>
    <AbsoluteFill style={{transform: `scale(${scale})`, transformOrigin, opacity, willChange: 'transform, opacity'}}>
      {children}
    </AbsoluteFill>
  </AbsoluteFill>;
};
