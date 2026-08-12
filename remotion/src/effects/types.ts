import type {AnimationEffect} from '../types';

export type EffectProps = {
  animation: AnimationEffect | null | undefined;
  children: React.ReactNode;
};
