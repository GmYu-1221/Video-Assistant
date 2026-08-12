import type {ReactElement} from 'react';
import {TransitionSeries, linearTiming} from '@remotion/transitions';
import {fade} from './fade';
import {flip} from './flip';
import {slide} from './slide';
import {wipe} from './wipe';
import {zoomBlur} from './zoom_blur';
import type {TransitionConfig} from '../types';

export const TransitionFactory = (transition: TransitionConfig, key: string): ReactElement => {
  const timing = linearTiming({durationInFrames: transition.duration_frames});
  switch (transition.type) {
    case 'slide':
      return <TransitionSeries.Transition key={key} timing={timing} presentation={slide({direction: transition.direction === 'from-left' ? 'from-left' : 'from-right'})} />;
    case 'wipe':
      return <TransitionSeries.Transition key={key} timing={timing} presentation={wipe({direction: transition.direction === 'from-right' ? 'from-right' : 'from-left'})} />;
    case 'flip':
      return <TransitionSeries.Transition key={key} timing={timing} presentation={flip({direction: transition.direction === 'from-left' ? 'from-left' : 'from-right'})} />;
    case 'zoom_blur':
      return <TransitionSeries.Transition key={key} timing={timing} presentation={zoomBlur({rotation: 0.15})} />;
    case 'fade':
    default:
      return <TransitionSeries.Transition key={key} timing={timing} presentation={fade()} />;
  }
};
