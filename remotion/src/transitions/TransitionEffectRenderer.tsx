import type {ReactElement} from 'react';
import {TransitionSeries, linearTiming} from '@remotion/transitions';
import {GlassShatter} from './presentations/glass-shatter';
import {ShakeTransition} from './presentations/shake';

export type TransitionEffectPlan = {
  from_asset_id: string;
  to_asset_id: string;
  type: 'glass_shatter_transition' | 'shake_transition';
  duration_frames: number;
  params: {fragment_count?: number; impact_origin?: 'center'|'left'|'right'|'top'|'bottom'; intensity?: number; motion_blur?: boolean};
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

/** Registry intentionally separate from baseline TransitionConfig rendering. */
export const TransitionEffectRegistry: Record<TransitionEffectPlan['type'], TransitionEffectBuilder> = {
  glass_shatter_transition: glassShatterTransition,
  shake_transition: shakeTransition,
};

/** Render an LLM-selected creative transition after its schema has validated it. */
export const TransitionEffectRenderer = (effect: TransitionEffectPlan, key: string): ReactElement => (
  TransitionEffectRegistry[effect.type](effect, key)
);
