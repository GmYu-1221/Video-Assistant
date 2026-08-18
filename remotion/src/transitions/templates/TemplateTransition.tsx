import React from 'react';
import type {TransitionPresentationComponentProps} from '@remotion/transitions';
import {TemplatePresentationRegistry} from './registry';
import type {TemplateTransitionProps} from './types';

export const TemplateTransition: React.FC<TransitionPresentationComponentProps<TemplateTransitionProps>> = (props) => {
  const Template = TemplatePresentationRegistry[props.passedProps.template_id];
  if (!Template) {
    throw new Error(`Unknown transition template: ${props.passedProps.template_id}`);
  }
  return <Template {...props} parameters={props.passedProps.parameters ?? {}} />;
};
