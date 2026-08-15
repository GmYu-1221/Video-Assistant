import React from 'react';
import {getFontFamily, resolveFontById, TypographyRole} from '../fonts/registry';

const SIZES: Record<string, number> = {display: 72, headline: 54, body: 36, caption: 30, metadata: 26, quote: 44, numeric: 60};
export const TextBlockRenderer: React.FC<{block: any; content: string}> = ({block, content}) => {
  const font = resolveFontById(block.font_id, block.typography_role as TypographyRole);
  return <div data-layout-block={block.block_id} data-font-id={font.id} style={{position:'absolute', left:block.bbox.x, top:block.bbox.y, width:block.bbox.width, height:block.bbox.height, color:block.color, fontFamily:getFontFamily(font.id, block.typography_role), fontSize:SIZES[block.typography_role] ?? 36, fontWeight:block.weight === 'bold' ? 700 : block.weight === 'medium' ? 500 : 400, lineHeight:1.28, whiteSpace:'pre-wrap', overflowWrap:'anywhere', wordBreak:'break-word', overflow:'visible', textAlign:block.alignment, zIndex:block.z_index}}>{content}</div>;
};
