import type {ReactElement} from 'react';
import {TransitionSeries, linearTiming, linearBlur, pushCut} from '@remotion/transitions';
import type {TransitionPresentation} from '@remotion/transitions';
import {fade} from './fade';
import {flip} from './flip';
import {slide} from './slide';
import {wipe} from './wipe';
import {zoomBlur} from './zoom_blur';
import {flash} from './flash';
import {push} from './push';
import {whip} from './whip';
import {zoomCut} from './zoom-cut';
import {spin} from './spin';
import {glitch} from './glitch';
import type {TransitionConfig} from '../types';

type TransitionBuilder = (config: TransitionConfig, key: string) => ReactElement;
const timing = (config: TransitionConfig) => linearTiming({durationInFrames: config.duration_frames});
const element = <P extends Record<string, unknown>>(key: string, config: TransitionConfig, presentation: TransitionPresentation<P>): ReactElement => <TransitionSeries.Transition key={key} timing={timing(config)} presentation={presentation} />;
const direction = (config: TransitionConfig): 'from-left' | 'from-right' => config.direction === 'from-left' ? 'from-left' : 'from-right';

export const TransitionRegistry: Record<string, TransitionBuilder> = {
  fade: (c, k) => element(k, c, fade()), crossfade: (c, k) => element(k, c, fade()), dissolve: (c, k) => element(k, c, fade()),
  slide: (c, k) => element(k, c, slide({direction: direction(c)})), slide_left: (c, k) => element(k, c, slide({direction: 'from-left'})), slide_right: (c, k) => element(k, c, slide({direction: 'from-right'})), slide_up: (c, k) => element(k, c, slide({direction: 'from-left'})), slide_down: (c, k) => element(k, c, slide({direction: 'from-right'})),
  wipe: (c, k) => element(k, c, wipe({direction: direction(c)})), wipe_left: (c, k) => element(k, c, wipe({direction: 'from-left'})), wipe_right: (c, k) => element(k, c, wipe({direction: 'from-right'})), wipe_up: (c, k) => element(k, c, wipe({direction: 'from-left'})), wipe_down: (c, k) => element(k, c, wipe({direction: 'from-right'})),
  // Headless rendering has no guaranteed WebGL2 context; keep these aliases stable and deterministic.
  zoom_in: (c, k) => element(k, c, fade()), zoom_out: (c, k) => element(k, c, fade()), zoom_blur: (c, k) => element(k, c, zoomBlur({rotation: 0.15})), zoom_crossfade: (c, k) => element(k, c, fade()),
  push_left: (c, k) => element(k, c, pushCut({incomingStartScale: 1.08})), push_right: (c, k) => element(k, c, pushCut({incomingStartScale: 1.08})), push_up: (c, k) => element(k, c, pushCut({incomingStartScale: 1.08})), push_down: (c, k) => element(k, c, pushCut({incomingStartScale: 1.08})),
  push: (c, k) => element(k, c, push({incomingStartScale: 1.08})), whip: (c, k) => element(k, c, whip({direction: direction(c)})), zoom_cut: (c, k) => element(k, c, zoomCut()), spin: (c, k) => element(k, c, spin({direction: direction(c)})), glitch: (c, k) => element(k, c, glitch({direction: direction(c)})),
  circle: (c, k) => element(k, c, wipe({direction: 'from-left'})), rectangle: (c, k) => element(k, c, wipe({direction: 'from-left'})), diagonal: (c, k) => element(k, c, wipe({direction: 'from-left'})), diagonal_reverse: (c, k) => element(k, c, wipe({direction: 'from-right'})), iris: (c, k) => element(k, c, wipe({direction: 'from-left'})), radial: (c, k) => element(k, c, wipe({direction: 'from-right'})),
  flip: (c, k) => element(k, c, flip({direction: direction(c)})), flip_x: (c, k) => element(k, c, flip({direction: 'from-left'})), flip_y: (c, k) => element(k, c, flip({direction: 'from-right'})), rotate: (c, k) => element(k, c, flip({direction: 'from-right'})), cube_left: (c, k) => element(k, c, flip({direction: 'from-left'})), cube_right: (c, k) => element(k, c, flip({direction: 'from-right'})),
  blur: (c, k) => element(k, c, linearBlur({})), blur_zoom: (c, k) => element(k, c, linearBlur({})), flash: (c, k) => element(k, c, flash()), light_leak: (c, k) => element(k, c, fade()), white_flash: (c, k) => element(k, c, flash()), black_flash: (c, k) => element(k, c, fade()), digital_wipe: (c, k) => element(k, c, wipe({direction: 'from-right'})), rgb_split: (c, k) => element(k, c, fade()), scanline: (c, k) => element(k, c, wipe({direction: 'from-left'})),
};

export const TransitionFactory = (transition: TransitionConfig, key: string): ReactElement => (TransitionRegistry[transition.type] ?? TransitionRegistry.fade)(transition, key);
