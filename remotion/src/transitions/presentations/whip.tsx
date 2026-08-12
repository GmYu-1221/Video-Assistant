import {AbsoluteFill} from 'remotion';
import {presentation} from './types';
export const whip = () => presentation(({children, presentationProgress, presentationDirection}) => <AbsoluteFill style={{transform:`translateX(${presentationDirection === 'entering' ? 100 - presentationProgress * 100 : -presentationProgress * 100}%)`,filter:`blur(${Math.sin(presentationProgress * Math.PI) * 7}px)`}}>{children}</AbsoluteFill>);
