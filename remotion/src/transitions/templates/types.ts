import type {ComponentType} from 'react';
import type {TransitionPresentationComponentProps} from '@remotion/transitions';

export type TemplateParameterValue =
  | boolean
  | number
  | string
  | null
  | TemplateParameterValue[]
  | {[key: string]: TemplateParameterValue};

export type TemplateParameters = Record<string, TemplateParameterValue>;

export type TemplateTransitionProps = {
  template_id: string;
  parameters?: TemplateParameters;
};

export type TemplatePresentationProps = TransitionPresentationComponentProps<TemplateTransitionProps> & {
  parameters: TemplateParameters;
};

export type TemplatePresentationComponent = ComponentType<TemplatePresentationProps>;
