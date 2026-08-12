import {AbsoluteFill} from 'remotion';
import {presentation} from './types';
export const digitalWipe = () => presentation(({children, presentationProgress, presentationDirection}) => <AbsoluteFill style={{clipPath:`inset(0 ${presentationDirection === 'entering' ? 100 - presentationProgress * 100 : presentationProgress * 100}% 0 0)`}}>{children}</AbsoluteFill>);
