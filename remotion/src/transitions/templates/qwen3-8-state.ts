export type Qwen38Parameters = {
  blur_strength?: number;
  float_distance?: number;
  recovery_speed?: number;
  opacity_start?: number;
};

export type Qwen38TransitionState = {
  blurPx: number;
  translateYPct: number;
  opacity: number;
  blurEndProgress: number;
  positionEndProgress: number;
};

export const QWEN38_DEFAULT_PARAMETERS: Required<Qwen38Parameters> = {
  blur_strength: 0.8,
  float_distance: 0.55,
  recovery_speed: 0.7,
  opacity_start: 0.88,
};

const clamp01 = (value: number): number => Math.min(1, Math.max(0, value));

const finiteParameter = (
  parameters: Record<string, unknown>,
  key: keyof Qwen38Parameters,
): number => {
  const value = parameters[key];
  return typeof value === 'number' && Number.isFinite(value)
    ? clamp01(value)
    : QWEN38_DEFAULT_PARAMETERS[key];
};

const easeOutCubic = (progress: number): number => 1 - (1 - progress) ** 3;
const easeOutSine = (progress: number): number => Math.sin((progress * Math.PI) / 2);

export const getQwen38TransitionState = (
  progress: number,
  parameters: Record<string, unknown> = {},
): Qwen38TransitionState => {
  const normalizedProgress = clamp01(progress);
  const blurStrength = finiteParameter(parameters, 'blur_strength');
  const floatDistance = finiteParameter(parameters, 'float_distance');
  const recoverySpeed = finiteParameter(parameters, 'recovery_speed');
  const opacityStart = finiteParameter(parameters, 'opacity_start');

  // These defaults mirror the HTML reference: 58px blur, 1.6% downward
  // offset, blur end at 36%, position end at 82%, and opacity end at 16%.
  // Recovery speed only nudges the two settle points while preserving their
  // required ordering and the reference default exactly.
  const blurEndProgress = clamp01(0.36 + (0.7 - recoverySpeed) * 0.1);
  const positionEndProgress = clamp01(0.82 + (0.7 - recoverySpeed) * 0.1);
  const opacityEndProgress = 0.16;

  const blurProgress = clamp01(normalizedProgress / blurEndProgress);
  const positionProgress = clamp01(normalizedProgress / positionEndProgress);
  const opacityProgress = clamp01(normalizedProgress / opacityEndProgress);
  const initialBlurPx = blurStrength * 72.5;
  const initialOffsetPct = floatDistance * (1.6 / 0.55);

  return {
    blurPx: normalizedProgress >= blurEndProgress
      ? 0
      : initialBlurPx * (1 - easeOutCubic(blurProgress)),
    translateYPct: normalizedProgress >= positionEndProgress
      ? 0
      : initialOffsetPct * (1 - easeOutSine(positionProgress)),
    opacity: normalizedProgress >= opacityEndProgress
      ? 1
      : opacityStart + (1 - opacityStart) * easeOutCubic(opacityProgress),
    blurEndProgress,
    positionEndProgress,
  };
};
