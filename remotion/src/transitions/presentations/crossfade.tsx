import {AbsoluteFill} from 'remotion';
import {presentation} from './types';
export const crossfade = () => presentation(({children, presentationProgress, presentationDirection}) => <AbsoluteFill style={{opacity: presentationDirection === 'entering' ? presentationProgress : 1 - presentationProgress}}>{children}</AbsoluteFill>);
