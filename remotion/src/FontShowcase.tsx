import React from 'react';
import {AbsoluteFill} from 'remotion';
import {FONT_REGISTRY, getFontFamily} from './fonts';

const samples = [
  {kind: 'headline', text: '人工智能正在改变创作方式'},
  {kind: 'latin', text: 'GitHub / AI / Qwen 3.8'},
  {kind: 'numeric', text: '1234567890'},
];

export const FontShowcase: React.FC = () => (
  <AbsoluteFill style={{backgroundColor: '#101010', color: '#f4f1ea', padding: '52px 60px', fontFamily: getFontFamily()}}>
    <div style={{fontSize: 24, color: '#9aa09a', marginBottom: 28}}>Typography Font Registry</div>
    {FONT_REGISTRY.map((font) => (
      <div key={font.id} style={{borderTop: '1px solid #343434', padding: '24px 0 28px', fontFamily: getFontFamily(font.id, 'headline')}}>
        <div style={{fontSize: 22, color: '#a4c639', marginBottom: 12, fontFamily: getFontFamily('noto-sans-sc', 'caption')}}>
          {font.family} / {font.id}
        </div>
        {samples.map((sample) => (
          <div key={`${font.id}-${sample.kind}`} style={{fontSize: sample.kind === 'headline' ? 42 : 34, lineHeight: 1.25, marginBottom: 4}}>
            {sample.text}
          </div>
        ))}
      </div>
    ))}
  </AbsoluteFill>
);
