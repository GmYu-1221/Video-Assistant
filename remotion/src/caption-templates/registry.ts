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
    media: {x: 0, y: 655, width: 1080, height: 610, fit: 'contain'},
    slots: [
      {slot_id: 'title_primary', x: 60, y: 92, width: 960, height: 96, fontSize: 62, color: '#FFD83D', maxLines: 1, kind: 'headline'},
      {slot_id: 'title_secondary', x: 60, y: 210, width: 960, height: 108, fontSize: 58, color: '#FFD83D', maxLines: 2, kind: 'headline'},
      {slot_id: 'title_tertiary', x: 60, y: 352, width: 960, height: 84, fontSize: 48, color: '#FFFFFF', maxLines: 1, kind: 'headline'},
      {slot_id: 'summary', x: 80, y: 1325, width: 920, height: 500, fontSize: 36, color: '#FFFFFF', maxLines: 8, kind: 'summary'},
    ],
  },
};

export const getCaptionTemplate = (templateId: string): CaptionTemplateDefinition => {
  const template = CaptionTemplateRegistry[templateId];
  if (!template) throw new Error(`Unknown caption template: ${templateId}`);
  return template;
};
