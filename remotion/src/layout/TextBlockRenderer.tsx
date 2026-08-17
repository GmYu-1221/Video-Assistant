import React from 'react';
import {getFontFamily, resolveFontById, TypographyRole} from '../fonts/registry';

const SIZES: Record<string, number> = {display: 72, headline: 54, body: 36, caption: 30, metadata: 26, quote: 44, numeric: 60};
const OUTLINES: Record<string, string> = {none: '0px transparent', dark_thin: '1.5px #07090B', dark_strong: '3px #07090B'};
const SHADOWS: Record<string, string> = {none: 'none', soft: '0 2px 8px rgba(0,0,0,0.72)', strong: '0 3px 12px rgba(0,0,0,0.92)'};

const emphasize = (content: string, phrases: string[], color?: string | null) => {
  const usable = [...new Set((phrases ?? []).filter((phrase) => phrase && content.includes(phrase)))].sort((a, b) => b.length - a.length);
  if (!usable.length || !color) return content;
  const pattern = new RegExp(`(${usable.map((value) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'g');
  return content.split(pattern).map((part, index) => usable.includes(part) ? <span key={`${part}-${index}`} style={{color}}>{part}</span> : part);
};

export const TextBlockRenderer: React.FC<{block: any; content: string}> = ({block, content}) => {
  const font = resolveFontById(block.font_id, block.typography_role as TypographyRole);
  const outline = block.outline ?? 'none';
  const shadow = block.shadow ?? 'none';
  return <div data-layout-block={block.block_id} data-font-id={font.id} data-outline={outline} data-caption-style={block.caption_style_intent ?? 'explanatory'} style={{position:'absolute', left:block.bbox.x, top:block.bbox.y, width:block.bbox.width, height:block.bbox.height, color:block.color, fontFamily:getFontFamily(font.id, block.typography_role), fontSize:SIZES[block.typography_role] ?? 36, fontWeight:block.weight === 'bold' ? 700 : block.weight === 'medium' ? 500 : 400, lineHeight:1.28, whiteSpace:'pre-wrap', overflowWrap:'anywhere', wordBreak:'break-word', overflow:'visible', textAlign:block.alignment, WebkitTextStroke:OUTLINES[outline] ?? OUTLINES.none, paintOrder:'stroke fill', textShadow:SHADOWS[shadow] ?? SHADOWS.none, letterSpacing:block.letter_spacing === 'relaxed' ? 1 : 0, zIndex:block.z_index}}>{emphasize(content, block.emphasis ?? [], block.emphasis_color)}</div>;
};
