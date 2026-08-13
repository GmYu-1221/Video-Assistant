import {AbsoluteFill, interpolate, spring, useVideoConfig} from 'remotion';
import type {TransitionPresentationComponentProps} from '@remotion/transitions';

export type BlurTransitionVariant = 'gaussian_blur_transition' | 'directional_blur_transition' | 'pixel_blur_transition' | 'bokeh_blur_transition' | 'water_ripple_transition';
export type BlurTransitionProps = {
  blur_type?: 'gaussian' | 'directional' | 'pixelate' | 'bokeh' | 'mist' | 'water_ripple';
  direction?: 'horizontal' | 'vertical' | 'radial' | 'left' | 'right' | 'up' | 'down';
  intensity?: number;
  softness?: number;
  motion_blur?: boolean;
};

export const BlurTransition: React.FC<TransitionPresentationComponentProps<BlurTransitionProps> & {variant: BlurTransitionVariant}> = ({children, presentationDirection, presentationProgress, passedProps, variant}) => {
  const {fps} = useVideoConfig();
  const intensity = Math.max(0, Math.min(1, passedProps.intensity ?? 0.7));
  const softness = Math.max(0, Math.min(1, passedProps.softness ?? 0.6));
  const local = presentationDirection === 'exiting' ? presentationProgress : 1 - presentationProgress;
  const peak = Math.sin(presentationProgress * Math.PI);
  const settle = spring({frame: Math.round(presentationProgress * 18), fps, config: {damping: 200, stiffness: 100}});
  const blurPx = interpolate(peak, [0, 1], [0, 8 + intensity * 22], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const direction = passedProps.direction ?? 'horizontal';
  const directionalX = direction === 'left' ? -1 : direction === 'right' ? 1 : direction === 'horizontal' ? 1 : 0;
  const directionalY = direction === 'up' ? -1 : direction === 'down' ? 1 : direction === 'vertical' ? 1 : 0;
  const translate = variant === 'directional_blur_transition'
    ? `translate(${directionalX * peak * intensity * 3}%, ${directionalY * peak * intensity * 3}%)`
    : variant === 'water_ripple_transition'
      ? `scale(${1 + peak * intensity * 0.025})`
      : 'none';
  const pixelate = variant === 'pixel_blur_transition' ? Math.max(0.08, 1 - peak * intensity * 0.82) : 1;
  const bokehOpacity = variant === 'bokeh_blur_transition' ? peak * (0.16 + intensity * 0.26) : 0;
  const ripple = variant === 'water_ripple_transition'
    ? `radial-gradient(circle at 50% 50%, transparent ${Math.max(0, peak * 55 - 8)}%, rgba(255,255,255,${0.18 * peak}) ${peak * 55}%, transparent ${peak * 55 + 10}%)`
    : undefined;
  const filter = variant === 'pixel_blur_transition'
    ? `blur(${blurPx * 0.25}px) contrast(${1 + peak * intensity * 0.2})`
    : `blur(${blurPx * (passedProps.motion_blur ? 1.2 : 1)}px)`;

  return <AbsoluteFill style={{overflow: 'hidden'}}>
    <AbsoluteFill style={{transform: translate, filter, opacity: interpolate(local, [0, 1], [0.98, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}), clipPath: variant === 'pixel_blur_transition' ? `inset(0 round ${Math.round((1 - pixelate) * 24)}px)` : undefined}}>{children}</AbsoluteFill>
    {variant === 'pixel_blur_transition' && <AbsoluteFill style={{pointerEvents: 'none', opacity: peak * intensity * 0.18, backgroundImage: 'linear-gradient(90deg, rgba(255,255,255,.22) 1px, transparent 1px), linear-gradient(rgba(255,255,255,.22) 1px, transparent 1px)', backgroundSize: `${Math.max(4, Math.round(28 * pixelate))}px ${Math.max(4, Math.round(28 * pixelate))}px`, mixBlendMode: 'overlay'}} />}
    {variant === 'bokeh_blur_transition' && <AbsoluteFill style={{pointerEvents: 'none', opacity: bokehOpacity * settle, background: 'radial-gradient(circle at 24% 32%, rgba(255,235,190,.9) 0 4%, transparent 13%), radial-gradient(circle at 72% 62%, rgba(180,220,255,.8) 0 5%, transparent 16%), radial-gradient(circle at 52% 46%, rgba(255,255,255,.7) 0 3%, transparent 11%)', filter: `blur(${10 + softness * 18}px)`, mixBlendMode: 'screen'}} />}
    {ripple && <AbsoluteFill style={{pointerEvents: 'none', background: ripple, mixBlendMode: 'screen', opacity: peak * (0.5 + softness * 0.5)}} />}
  </AbsoluteFill>;
};
