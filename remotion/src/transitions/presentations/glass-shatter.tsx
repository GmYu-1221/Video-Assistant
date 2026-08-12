import {AbsoluteFill, interpolate} from 'remotion';
import type {TransitionPresentationComponentProps} from '@remotion/transitions';

type GlassShatterProps = {
  fragment_count?: number;
  impact_origin?: 'center' | 'left' | 'right' | 'top' | 'bottom';
  motion_blur?: boolean;
  backgroundColor?: {r: number; g: number; b: number};
};

const originFor = (origin: GlassShatterProps['impact_origin']) => {
  if (origin === 'left') return {x: 0, y: .5};
  if (origin === 'right') return {x: 1, y: .5};
  if (origin === 'top') return {x: .5, y: 0};
  if (origin === 'bottom') return {x: .5, y: 1};
  return {x: .5, y: .5};
};

export const GlassShatter: React.FC<TransitionPresentationComponentProps<GlassShatterProps>> = ({children, presentationProgress, presentationDirection, passedProps}) => {
  const count = Math.max(12, Math.min(96, Math.round(passedProps.fragment_count ?? 48)));
  const columns = Math.max(4, Math.ceil(Math.sqrt(count * 16 / 9)));
  const rows = Math.max(3, Math.ceil(count / columns));
  const origin = originFor(passedProps.impact_origin);
  const progress = interpolate(presentationProgress, [0, 1], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  if (presentationDirection === 'entering') {
    return <AbsoluteFill style={{opacity: interpolate(progress, [0, .32, 1], [0, .72, 1], {extrapolateRight: 'clamp'})}}>{children}</AbsoluteFill>;
  }

  return <AbsoluteFill style={{overflow: 'hidden'}}>
    {Array.from({length: count}, (_, index) => {
      const column = index % columns;
      const row = Math.floor(index / columns);
      const centerX = (column + .5) / columns;
      const centerY = (row + .5) / rows;
      const dx = centerX - origin.x;
      const dy = centerY - origin.y;
      const distance = Math.min(1, Math.hypot(dx, dy) * 1.45);
      const local = interpolate(progress, [distance * .38, .38 + distance * .36, 1], [0, 0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
      const travel = 70 + (index % 7) * 19;
      const rotation = (index % 2 ? 1 : -1) * (95 + (index % 5) * 22) * local;
      const clipX = `${(column / columns) * 100}%`;
      const clipY = `${(row / rows) * 100}%`;
      const clipRight = `${100 - ((column + 1) / columns) * 100}%`;
      const clipBottom = `${100 - ((row + 1) / rows) * 100}%`;
      return <AbsoluteFill key={index} style={{
        clipPath: `inset(${clipY} ${clipRight} ${clipBottom} ${clipX})`,
        opacity: 1 - local,
        transform: `translate(${dx * travel * local}px, ${dy * travel * local + local * local * 85}px) rotate(${rotation}deg) scale(${1 - local * .18})`,
        transformOrigin: `${centerX * 100}% ${centerY * 100}%`,
        filter: passedProps.motion_blur ? `blur(${local * 2.2}px)` : undefined,
      }}>{children}</AbsoluteFill>;
    })}
  </AbsoluteFill>;
};
