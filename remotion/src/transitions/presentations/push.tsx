import {AbsoluteFill} from 'remotion';
import {presentation} from './types';
export const push = () => presentation(({children, presentationProgress, presentationDirection}) => <AbsoluteFill style={{transform:`translateX(${presentationDirection === 'entering' ? 100 - presentationProgress * 100 : -presentationProgress * 100}%)`}}>{children}</AbsoluteFill>);
