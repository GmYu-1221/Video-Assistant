import type {ReactElement} from 'react';
import {TransitionSeries, linearTiming} from '@remotion/transitions';
import type {TransitionPresentation, TransitionPresentationComponentProps} from '@remotion/transitions';
import {fade} from './fade'; import {flip} from './flip'; import {slide} from './slide'; import {wipe} from './wipe'; import {zoomBlur} from './zoom_blur';
import {crossfade} from './presentations/crossfade'; import {blackFlash} from './presentations/black_flash'; import {whiteFlash} from './presentations/white_flash'; import {push} from './presentations/push'; import {whip} from './presentations/whip'; import {digitalWipe} from './presentations/digital_wipe'; import {iris} from './presentations/iris'; import {clockWipe} from './presentations/clock_wipe'; import {blinds} from './presentations/blinds'; import {pixelReveal} from './presentations/pixel_reveal'; import {glitch} from './presentations/glitch'; import {lightLeak} from './presentations/light_leak';
import type {TransitionConfig} from '../types'; import {TransitionMetadataRegistry} from './metadata';
import {AbsoluteFill} from 'remotion';
type Builder = (config: TransitionConfig, key: string) => ReactElement;
const timing = (c: TransitionConfig) => linearTiming({durationInFrames: c.duration_frames});
const element = <P extends Record<string, unknown>>(key: string, c: TransitionConfig, p: TransitionPresentation<P>): ReactElement => {
  const presentation = {...p, component: (props: TransitionPresentationComponentProps<P>) => { const color = c.background_color; return <AbsoluteFill style={{backgroundColor: color ? `rgb(${color.r}, ${color.g}, ${color.b})` : '#111827'}}><p.component {...props} /></AbsoluteFill>; }, props: {...p.props, backgroundColor: c.background_color}} as TransitionPresentation<P>;
  return <TransitionSeries.Transition key={key} timing={timing(c)} presentation={presentation}/>;
};
const direction = (c: TransitionConfig): 'from-left'|'from-right' => c.direction === 'from-left' ? 'from-left' : 'from-right';
export const TransitionRegistry: Record<string, Builder> = {
  fade:(c,k)=>element(k,c,fade()), crossfade:(c,k)=>element(k,c,crossfade()), black_flash:(c,k)=>element(k,c,blackFlash()), white_flash:(c,k)=>element(k,c,whiteFlash()), push:(c,k)=>element(k,c,push()), whip:(c,k)=>element(k,c,whip()), digital_wipe:(c,k)=>element(k,c,digitalWipe()), iris:(c,k)=>element(k,c,iris()), clock_wipe:(c,k)=>element(k,c,clockWipe()), blinds:(c,k)=>element(k,c,blinds()), pixel_reveal:(c,k)=>element(k,c,pixelReveal()), glitch:(c,k)=>element(k,c,glitch()), light_leak:(c,k)=>element(k,c,lightLeak()),
  slide:(c,k)=>element(k,c,slide({direction:direction(c)})), slide_left:(c,k)=>element(k,c,slide({direction:'from-left'})), slide_right:(c,k)=>element(k,c,slide({direction:'from-right'})), wipe:(c,k)=>element(k,c,wipe({direction:direction(c)})), wipe_left:(c,k)=>element(k,c,wipe({direction:'from-left'})), wipe_right:(c,k)=>element(k,c,wipe({direction:'from-right'})), flip:(c,k)=>element(k,c,flip({direction:direction(c)})), zoom_blur:(c,k)=>element(k,c,zoomBlur({rotation:.15})),
};
export const TransitionFactory = (transition: TransitionConfig, key: string): ReactElement => (TransitionRegistry[transition.type] ?? TransitionRegistry.fade)(transition,key);
export {TransitionMetadataRegistry};
