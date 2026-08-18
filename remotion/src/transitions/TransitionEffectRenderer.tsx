import React, {type ReactElement} from 'react';
import {TransitionSeries, linearTiming} from '@remotion/transitions';
import {TemplateTransition} from './templates/TemplateTransition';
import type {TemplateParameters} from './templates/types';

export type TransitionEffectPlan = {
  from_asset_id: string;
  to_asset_id: string;
  type: 'template_transition';
  duration_frames: number;
  params: {
    template_id: string;
    parameters?: TemplateParameters;
  };
};

type TransitionEffectBuilder = (effect: TransitionEffectPlan, key: string) => ReactElement;

const templateTransition: TransitionEffectBuilder = (effect, key) => (
  <TransitionSeries.Transition
    key={key}
    timing={linearTiming({durationInFrames: effect.duration_frames})}
    presentation={{component: TemplateTransition, props: effect.params}}
  />
);

export const TransitionEffectRegistry: Record<TransitionEffectPlan['type'], TransitionEffectBuilder> = {
  template_transition: templateTransition,
};

export const TransitionEffectRenderer = (effect: TransitionEffectPlan, key: string): ReactElement => {
  const builder = TransitionEffectRegistry[effect.type];
  if (!builder) {
    throw new Error(`Unknown creative transition effect: ${effect.type}`);
  }
  return builder(effect, key);
};
