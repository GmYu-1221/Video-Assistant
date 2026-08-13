import type {ReactElement} from 'react';
import {TransitionSeries, linearTiming} from '@remotion/transitions';
import type {TransitionPresentationComponentProps} from '@remotion/transitions';
import {GlassShatter} from './presentations/glass-shatter';
import {ShakeTransition} from './presentations/shake';
import {BlurTransition, type BlurTransitionProps, type BlurTransitionVariant} from './blur/BlurTransition';
import {ZoomThroughTransition, type ZoomThroughTransitionProps} from './zoom/ZoomThroughTransition';

export type TransitionEffectPlan = {
  from_asset_id: string;
  to_asset_id: string;
  type: 'card_flip_transition' | 'glass_shatter_transition' | 'shake_transition' | 'zoom_through_transition' | BlurTransitionVariant;
  duration_frames: number;
  params: {fragment_count?: number; impact_origin?: 'center'|'left'|'right'|'top'|'bottom'; intensity?: number; motion_blur?: boolean; rotation_axis?: 'X'|'Y'; perspective?: number} & BlurTransitionProps & ZoomThroughTransitionProps;
};

type TransitionEffectBuilder = (effect: TransitionEffectPlan, key: string) => ReactElement;

const glassShatterTransition = (effect: TransitionEffectPlan, key: string): ReactElement => (
  <TransitionSeries.Transition
    key={key}
    timing={linearTiming({durationInFrames: effect.duration_frames})}
    presentation={{component: GlassShatter, props: effect.params}}
  />
);
const shakeTransition = (effect: TransitionEffectPlan, key: string): ReactElement => (
  <TransitionSeries.Transition
    key={key}
    timing={linearTiming({durationInFrames: effect.duration_frames})}
    presentation={{component: ShakeTransition, props: effect.params}}
  />
);
const cardFlipTransition = (effect: TransitionEffectPlan, key: string): ReactElement => (
  <TransitionSeries.Transition key={key} timing={linearTiming({durationInFrames: effect.duration_frames})} presentation={{component: (({children, presentationProgress}: TransitionPresentationComponentProps<Record<string, never>>) => <div style={{perspective: Number(effect.params.perspective ?? 900), width: '100%', height: '100%', transform: `rotateY(${(1 - presentationProgress) * 180}deg)`, transformOrigin: 'center'}}>{children}</div>), props: {}}} />
);
const blurTransition = (variant: BlurTransitionVariant) => (effect: TransitionEffectPlan, key: string): ReactElement => (
  <TransitionSeries.Transition key={key} timing={linearTiming({durationInFrames: effect.duration_frames})} presentation={{component: (props: TransitionPresentationComponentProps<BlurTransitionProps>) => <BlurTransition {...props} variant={variant} />, props: effect.params}} />
);
const zoomThroughTransition = (effect: TransitionEffectPlan, key: string): ReactElement => (
  <TransitionSeries.Transition key={key} timing={linearTiming({durationInFrames: effect.duration_frames})} presentation={{component: ZoomThroughTransition, props: effect.params}} />
);

/** Registry intentionally separate from baseline TransitionConfig rendering. */
export const TransitionEffectRegistry: Record<TransitionEffectPlan['type'], TransitionEffectBuilder> = {
  card_flip_transition: cardFlipTransition,
  glass_shatter_transition: glassShatterTransition,
  shake_transition: shakeTransition,
  gaussian_blur_transition: blurTransition('gaussian_blur_transition'),
  directional_blur_transition: blurTransition('directional_blur_transition'),
  pixel_blur_transition: blurTransition('pixel_blur_transition'),
  bokeh_blur_transition: blurTransition('bokeh_blur_transition'),
  water_ripple_transition: blurTransition('water_ripple_transition'),
  zoom_through_transition: zoomThroughTransition,
};

/** Render an LLM-selected creative transition after its schema has validated it. */
export const TransitionEffectRenderer = (effect: TransitionEffectPlan, key: string): ReactElement => (
  TransitionEffectRegistry[effect.type](effect, key)
);
