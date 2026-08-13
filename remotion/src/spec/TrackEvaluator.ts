import {interpolate} from 'remotion';
import type {VisualSpecTrack} from '../types';

const easing = (name?: string) => name === 'easeOutCubic' ? (value: number) => 1 - Math.pow(1 - value, 3) : name === 'easeInOutQuad' ? (value: number) => value < 0.5 ? 2 * value * value : 1 - Math.pow(-2 * value + 2, 2) / 2 : (value: number) => value;

export const evaluateTrack = (track: VisualSpecTrack, frame: number): number => {
  const frames = track.keyframes.map((keyframe) => keyframe.frame);
  const values = track.keyframes.map((keyframe) => keyframe.value);
  if (frame <= frames[0]) return values[0];
  if (frame >= frames[frames.length - 1]) return values[values.length - 1];
  const index = frames.findIndex((value, position) => value <= frame && frame <= frames[position + 1]);
  const progress = (frame - frames[index]) / (frames[index + 1] - frames[index]);
  return interpolate(easing(track.keyframes[index + 1].easing)(progress), [0, 1], [values[index], values[index + 1]]);
};

export const trackValue = (tracks: VisualSpecTrack[] | undefined, property: string, frame: number, fallback: number): number => {
  const track = tracks?.find((candidate) => candidate.property === property);
  return track ? evaluateTrack(track, frame) : fallback;
};
