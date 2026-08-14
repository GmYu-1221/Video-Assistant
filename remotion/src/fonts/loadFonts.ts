import {continueRender, delayRender, staticFile} from 'remotion';
import {FONT_REGISTRY, FontDefinition} from './registry';

const loaded = new Set<string>();
const failed = new Set<string>();

export const loadRegisteredFonts = async (): Promise<void> => {
  const waitForFonts = delayRender('Loading registered local fonts');
  await Promise.all(FONT_REGISTRY.map(async (font) => {
    if (loaded.has(font.id) || failed.has(font.id)) return;
    try {
      const response = await fetch(staticFile(font.local_path));
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const face = new FontFace(font.family, await response.arrayBuffer(), {
        weight: String(font.weights[0]),
        display: 'block',
      });
      await face.load();
      (document.fonts as FontFaceSet & {add: (font: FontFace) => void}).add(face);
      loaded.add(font.id);
    } catch (error) {
      failed.add(font.id);
      console.warn(`[Font Registry] failed to load ${font.id}; fallback will be used`, error);
    }
  }));
  continueRender(waitForFonts);
};

export const isFontLoaded = (font: FontDefinition): boolean => loaded.has(font.id);
