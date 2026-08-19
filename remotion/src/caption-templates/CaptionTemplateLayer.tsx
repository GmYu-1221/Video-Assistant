import React from 'react';
import {Easing, interpolate, useCurrentFrame} from 'remotion';
import {getFontFamily} from '../fonts/registry';
import {getCaptionTemplate} from './registry';

export const CaptionTemplateLayer: React.FC<{plan:any;headlineFontId:string;bodyFontId:string}> = ({plan, headlineFontId, bodyFontId}) => {
  const frame = useCurrentFrame();
  if (!plan) return null;
  const template = getCaptionTemplate(plan.template_id);
  if (plan.template_version !== template.version) throw new Error(`Unsupported caption template version: ${plan.template_id}@${plan.template_version}`);
  const opacity = interpolate(frame, [0, 11], [0, 1], {extrapolateLeft:'clamp', extrapolateRight:'clamp', easing:Easing.bezier(0.16,1,0.3,1)});
  return <div data-caption-template={plan.template_id} style={{position:'absolute',inset:0,zIndex:31,pointerEvents:'none',opacity}}>
    <div data-caption-band="headline" style={{position:'absolute',left:0,top:0,width:1080,height:430,background:'rgba(5,7,9,.72)',zIndex:0}} />
    <div data-caption-band="summary" style={{position:'absolute',left:0,top:1040,width:1080,height:880,background:'rgba(5,7,9,.76)',zIndex:0}} />
    {(plan.global_bindings ?? []).map((binding:any) => {
      const box = template.slots.find((slot) => slot.slot_id === binding.slot_id);
      if (!box) throw new Error(`Unknown caption template slot: ${binding.slot_id}`);
      const title = box.kind === 'headline';
      return <div key={binding.slot_id} data-caption-slot={binding.slot_id} data-content-hash={binding.content_hash} style={{position:'absolute',left:box.x,top:box.y,width:box.width,height:box.height,zIndex:1,display:'flex',alignItems:'center',justifyContent:'center',overflow:'visible',overflowWrap:'anywhere',wordBreak:'break-word',whiteSpace:'pre-wrap',textAlign:'center',fontFamily:getFontFamily(title ? headlineFontId : bodyFontId, title ? 'headline' : 'body'),fontSize:box.fontSize,fontWeight:title?400:400,lineHeight:title?1.18:1.38,color:box.color,WebkitTextStroke:title?'2px #07090B':'0px transparent',paintOrder:'stroke fill',textShadow:title?'0 3px 12px rgba(0,0,0,.92)':'0 2px 8px rgba(0,0,0,.86)',letterSpacing:0}}>{binding.content}</div>;
    })}
  </div>;
};
