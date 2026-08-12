import type {ReactNode} from 'react';
import type {TransitionPresentation, TransitionPresentationComponentProps} from '@remotion/transitions';
import {AbsoluteFill} from 'remotion';

export type PresentationProps = {backgroundColor?: {r:number; g:number; b:number}};
export type PresentationInput = TransitionPresentationComponentProps<PresentationProps>;
export type Presentation = TransitionPresentation<PresentationProps>;
export const presentation = (component: (props: PresentationInput) => ReactNode): Presentation => ({component: (props: PresentationInput) => { const color = props.passedProps.backgroundColor; return <AbsoluteFill style={{backgroundColor: color ? `rgb(${color.r}, ${color.g}, ${color.b})` : '#111827'}}><AbsoluteFill>{component(props)}</AbsoluteFill></AbsoluteFill>; }, props: {}});
