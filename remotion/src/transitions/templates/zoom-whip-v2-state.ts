export type ZoomWhipParameters = {
  zoom?: number;
  distance?: number;
  blur?: number;
};

export type ZoomWhipState = {
  translateXPct: number;
  scale: number;
  blurPx: number;
  opacity: number;
};

export const ZOOM_WHIP_DEFAULT_PARAMETERS: Required<ZoomWhipParameters> = {
  zoom: 1.08,
  distance: 12,
  blur: 10,
};

const clamp = (value: number, min: number, max: number): number => Math.min(max, Math.max(min, value));
const numberParam = (parameters: Record<string, unknown>, key: keyof ZoomWhipParameters, fallback: number): number => {
  const value = parameters[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
};
const ease = (progress: number): number => 1 - (1 - clamp(progress, 0, 1)) ** 3;

export const getZoomWhipV2State = (
  progress: number,
  direction: 'entering' | 'exiting',
  parameters: Record<string, unknown> = {},
): ZoomWhipState => {
  const zoom = clamp(numberParam(parameters, 'zoom', ZOOM_WHIP_DEFAULT_PARAMETERS.zoom), 1, 1.2);
  const distance = clamp(numberParam(parameters, 'distance', ZOOM_WHIP_DEFAULT_PARAMETERS.distance), 3, 30);
  const blur = clamp(numberParam(parameters, 'blur', ZOOM_WHIP_DEFAULT_PARAMETERS.blur), 0, 24);
  const p = clamp(progress, 0, 1);
  if (direction === 'exiting') {
    const scaleProgress = p < 0.38 ? ease(p / 0.38) : p < 0.68 ? ease((p - 0.38) / 0.3) : 1;
    const translate = p < 0.38 ? distance * 0.18 * ease(p / 0.38) : p < 0.68
      ? distance * 0.18 + distance * 0.82 * ease((p - 0.38) / 0.3)
      : distance + distance * 0.55 * ease((p - 0.68) / 0.32);
    return {
      translateXPct: -translate,
      scale: 1 + (zoom - 1) * scaleProgress,
      blurPx: p < 0.68 ? blur * 0.18 * ease(p / 0.38) + blur * 0.82 * ease(Math.max(0, (p - 0.38) / 0.3)) : blur * (1 + 0.05 * ease((p - 0.68) / 0.32)),
      opacity: p < 0.68 ? 1 - 0.28 * ease(Math.max(0, (p - 0.38) / 0.3)) : 0.72 * (1 - ease((p - 0.68) / 0.32)),
    };
  }
  const scale = p < 0.72 ? zoom - (zoom - (1 + (zoom - 1) * 0.2)) * ease(p / 0.72) : 1;
  const translate = p < 0.34 ? distance * 1.55 - distance * 0.73 * ease(p / 0.34) : p < 0.72
    ? distance * 0.82 - distance * 0.85 * ease((p - 0.34) / 0.38)
    : 0;
  return {
    translateXPct: translate,
    scale,
    blurPx: p < 0.72 ? blur * (1.05 - 0.27 * ease(p / 0.34) - 0.66 * ease(Math.max(0, (p - 0.34) / 0.38))) : 0,
    opacity: p < 0.34 ? 0.42 * ease(p / 0.34) : 0.42 + 0.58 * ease((p - 0.34) / 0.38),
  };
};
