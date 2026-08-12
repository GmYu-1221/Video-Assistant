import type {ReactNode} from 'react';
import type {TransitionPresentation, TransitionPresentationComponentProps} from '@remotion/transitions';

export type PresentationProps = Record<string, never>;
export type PresentationInput = TransitionPresentationComponentProps<PresentationProps>;
export type Presentation = TransitionPresentation<PresentationProps>;
export const presentation = (component: (props: PresentationInput) => ReactNode): Presentation => ({component, props: {}});
