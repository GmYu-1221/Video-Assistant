import {AbsoluteFill} from 'remotion';
import {presentation} from './types';
export const iris = () => presentation(({children, presentationProgress, presentationDirection}) => <AbsoluteFill style={{clipPath:`circle(${(presentationDirection === 'entering' ? presentationProgress : 1 - presentationProgress) * 75}% at 50% 50%)`}}>{children}</AbsoluteFill>);
