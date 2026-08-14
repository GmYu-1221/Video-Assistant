import registryData from './font-registry.json';

export const TYPOGRAPHY_ROLES = ['display', 'headline', 'body', 'caption', 'quote', 'numeric', 'artistic'] as const;
export type TypographyRole = (typeof TYPOGRAPHY_ROLES)[number];

export type FontDefinition = {
  id: string;
  family: string;
  local_path: string;
  weights: number[];
  roles: TypographyRole[];
  moods: string[];
  styles: string[];
  best_for: string[];
  avoid_for: string[];
  supports_cjk: boolean;
  recommended_max_lines: number;
  fallback_family: string;
  license: string;
  source: string;
  is_artistic?: boolean;
};

export const FONT_REGISTRY = registryData as FontDefinition[];
export const DEFAULT_FONT_ID = 'noto-sans-sc';

const byId = new Map(FONT_REGISTRY.map((font) => [font.id, font]));
const byFamily = new Map(FONT_REGISTRY.map((font) => [font.family, font]));

export const getFont = (id: string): FontDefinition => {
  const font = byId.get(id);
  if (!font) throw new Error(`Unknown registered font: ${id}`);
  return font;
};

export const getFontFamily = (id = DEFAULT_FONT_ID, role?: TypographyRole): string => {
  const font = getFont(id);
  const fallbackOnly = role && (
    !font.roles.includes(role) ||
    (font.is_artistic && !['display', 'headline', 'quote'].includes(role))
  );
  if (fallbackOnly || font.family === font.fallback_family) return `"${font.fallback_family}"`;
  return `"${font.family}", "${font.fallback_family}"`;
};

export const getFallbackFont = (font: FontDefinition): FontDefinition => byFamily.get(font.fallback_family) ?? getFont(DEFAULT_FONT_ID);

export const validateFontRegistry = (): void => {
  const ids = new Set<string>();
  const families = new Set<string>();
  for (const font of FONT_REGISTRY) {
    if (ids.has(font.id)) throw new Error(`Duplicate font id: ${font.id}`);
    if (families.has(font.family)) throw new Error(`Duplicate font family: ${font.family}`);
    ids.add(font.id);
    families.add(font.family);
    if (!font.supports_cjk) throw new Error(`Registered showcase font must support CJK: ${font.id}`);
    if (!font.weights.length || !font.local_path) throw new Error(`Incomplete font definition: ${font.id}`);
    if (!byFamily.has(font.fallback_family)) throw new Error(`Missing fallback family: ${font.fallback_family}`);
    if (font.is_artistic && font.roles.some((role) => ['body', 'caption'].includes(role))) {
      throw new Error(`Artistic font cannot provide body/caption roles: ${font.id}`);
    }
  }
};

validateFontRegistry();
