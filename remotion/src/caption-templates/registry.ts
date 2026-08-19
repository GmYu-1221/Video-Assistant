export type CaptionSlotDefinition = {
  slot_id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  fontSize: number;
  color: string;
  maxLines: number;
  kind: 'headline' | 'summary';
};

export type CaptionTemplateDefinition = {
  template_id: string;
  version: string;
  media: {x: number; y: number; width: number; height: number; fit: 'contain'};
  slots: CaptionSlotDefinition[];
};

export const CaptionTemplateRegistry: Record<string, CaptionTemplateDefinition> = {
  reference_caption_v1: {
    template_id: 'reference_caption_v1',
    version: '1.0',
    media: {x: 0, y: 430, width: 1080, height: 610, fit: 'contain'},
    slots: [
      {slot_id: 'title_primary', x: 60, y: 48, width: 960, height: 112, fontSize: 62, color: '#FFD83D', maxLines: 1, kind: 'headline'},
      {slot_id: 'title_secondary', x: 60, y: 166, width: 960, height: 112, fontSize: 58, color: '#FFD83D', maxLines: 1, kind: 'headline'},
      {slot_id: 'title_tertiary', x: 60, y: 292, width: 960, height: 102, fontSize: 48, color: '#FFFFFF', maxLines: 1, kind: 'headline'},
      {slot_id: 'summary', x: 70, y: 1090, width: 940, height: 770, fontSize: 40, color: '#FFFFFF', maxLines: 8, kind: 'summary'},
    ],
  },
};

export const getCaptionTemplate = (templateId: string): CaptionTemplateDefinition => {
  const template = CaptionTemplateRegistry[templateId];
  if (!template) throw new Error(`Unknown caption template: ${templateId}`);
  return template;
};
