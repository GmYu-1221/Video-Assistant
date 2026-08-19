import React, {useLayoutEffect, useRef, useState} from 'react';
import {Video} from '@remotion/media';
import {AbsoluteFill, Artifact, Easing, Img, continueRender, delayRender, interpolate, useCurrentFrame} from 'remotion';
import {getFont, getFontFamily} from '../fonts/registry';

export type ReferenceCaptionTemplateProps = {
  topLines: [string, string, string];
  summary: string;
  mediaUrl: string;
  backgroundVideoUrl?: string | null;
  headlineFontId: string;
  bodyFontId: string;
  auditEnabled?: boolean;
};

const TOP_LINES = [
  {id: 'top-primary', y: 92, height: 96, size: 62, color: '#FFD83D'},
  {id: 'top-secondary', y: 210, height: 108, size: 58, color: '#FFD83D'},
  {id: 'top-tertiary', y: 352, height: 84, size: 48, color: '#FFFFFF'},
] as const;

const textWrap: React.CSSProperties = {
  whiteSpace: 'pre-wrap',
  overflowWrap: 'anywhere',
  wordBreak: 'break-word',
  overflow: 'visible',
  letterSpacing: 0,
};

const assertFontRole = (fontId: string, role: 'headline' | 'body'): void => {
  const font = getFont(fontId);
  if (!font.roles.includes(role) || (font.is_artistic && role === 'body')) {
    throw new Error(`Font ${fontId} cannot render ${role}`);
  }
};

export const ReferenceCaptionTemplate: React.FC<ReferenceCaptionTemplateProps> = (props) => {
  assertFontRole(props.headlineFontId, 'headline');
  assertFontRole(props.bodyFontId, 'body');
  const frame = useCurrentFrame();
  const rootRef = useRef<HTMLDivElement>(null);
  const auditHandle = useRef<number | null>(null);
  const [auditArtifact, setAuditArtifact] = useState<string | null>(null);
  if (props.auditEnabled && auditHandle.current === null) auditHandle.current = delayRender('Audit reference_caption_v1');

  useLayoutEffect(() => {
    if (props.auditEnabled && auditArtifact !== null && auditHandle.current !== null) {
      continueRender(auditHandle.current);
    }
  }, [auditArtifact, props.auditEnabled]);

  useLayoutEffect(() => {
    if (!props.auditEnabled) return;
    (async () => {
      await document.fonts.ready;
      const root = rootRef.current;
      if (!root) {
        setAuditArtifact(JSON.stringify({templateId: 'reference_caption_v1', frame, error: 'Template root is unavailable'}));
        return;
      }
      const canvas = root.getBoundingClientRect();
      const blocks = Array.from(root.querySelectorAll<HTMLElement>('[data-template-block]')).map((element) => {
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        let stackingElement: HTMLElement | null = element;
        let effectiveZIndex = 'auto';
        while (stackingElement && stackingElement !== root) {
          const candidate = getComputedStyle(stackingElement).zIndex;
          if (candidate !== 'auto') {
            effectiveZIndex = candidate;
            break;
          }
          stackingElement = stackingElement.parentElement;
        }
        return {
          id: element.dataset.templateBlock,
          x: rect.x - canvas.x,
          y: rect.y - canvas.y,
          width: rect.width,
          height: rect.height,
          scrollWidth: element.scrollWidth,
          clientWidth: element.clientWidth,
          scrollHeight: element.scrollHeight,
          clientHeight: element.clientHeight,
          fontFamily: style.fontFamily,
          fontSize: style.fontSize,
          textContent: element.textContent ?? '',
          zIndex: style.zIndex,
          effectiveZIndex,
        };
      });
      const headlineFamily = getFont(props.headlineFontId).family;
      const bodyFamily = getFont(props.bodyFontId).family;
      const audit = {
        templateId: 'reference_caption_v1',
        frame,
        fontsReady: document.fonts.status === 'loaded' && document.fonts.check(`16px "${headlineFamily}"`) && document.fonts.check(`16px "${bodyFamily}"`),
        topGroupOpacity: Number(getComputedStyle(root.querySelector<HTMLElement>('[data-top-group]')!).opacity),
        mediaObjectFit: getComputedStyle(root.querySelector<HTMLElement>('[data-media-image]')!).objectFit,
        mediaObjectPosition: getComputedStyle(root.querySelector<HTMLElement>('[data-media-image]')!).objectPosition,
        backgroundZIndex: getComputedStyle(root.querySelector<HTMLElement>('[data-template-background]')!).zIndex,
        blocks,
      };
      setAuditArtifact(JSON.stringify(audit));
    })().catch((error) => {
      console.error('[REFERENCE_CAPTION_AUDIT_ERROR]', error);
      setAuditArtifact(JSON.stringify({
        templateId: 'reference_caption_v1',
        frame,
        error: error instanceof Error ? error.message : String(error),
      }));
    });
  }, [frame, props.auditEnabled, props.bodyFontId, props.headlineFontId]);

  return <div ref={rootRef} style={{position: 'absolute', inset: 0, width: '100%', height: '100%', backgroundColor: '#07090B', overflow: 'hidden'}}>
    {props.auditEnabled && auditArtifact ? <Artifact filename={`reference-caption-audit-${frame}.json`} content={auditArtifact} /> : null}
    <AbsoluteFill data-template-background style={{zIndex: 0, overflow: 'hidden', backgroundColor: '#07090B'}}>
      {props.backgroundVideoUrl ? <Video src={props.backgroundVideoUrl} loop muted volume={0} objectFit="cover" style={{width: '100%', height: '100%'}} /> : null}
      <AbsoluteFill style={{backgroundColor: '#07090B', opacity: 0.64}} />
    </AbsoluteFill>

    <div data-top-group style={{position: 'absolute', inset: 0, zIndex: 10, opacity: interpolate(frame, [0, 11], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.bezier(0.16, 1, 0.3, 1)})}}>
      {TOP_LINES.map((line, index) => <div
        key={line.id}
        data-template-block={line.id}
        data-font-id={props.headlineFontId}
        style={{
          ...textWrap,
          position: 'absolute',
          left: 60,
          top: line.y,
          width: 960,
          height: line.height,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: line.color,
          fontFamily: getFontFamily(props.headlineFontId, 'headline'),
          fontSize: line.size,
          fontWeight: 400,
          lineHeight: 1.18,
          textAlign: 'center',
          WebkitTextStroke: '2px #07090B',
          paintOrder: 'stroke fill',
          textShadow: '0 3px 12px rgba(0,0,0,0.92)',
        }}
      >{props.topLines[index]}</div>)}
    </div>

    <div data-template-block="media" style={{position: 'absolute', left: 0, top: 655, width: 1080, height: 610, overflow: 'hidden', zIndex: 5, backgroundColor: '#F1F4F8'}}>
      {props.mediaUrl ? <Img data-media-image src={props.mediaUrl} style={{display: 'block', width: '100%', height: '100%', objectFit: 'contain', objectPosition: 'center'}} /> : null}
    </div>

    <div
      data-template-block="summary"
      data-font-id={props.bodyFontId}
      style={{
        ...textWrap,
        position: 'absolute',
        left: 80,
        top: 1325,
        width: 920,
        height: 500,
        zIndex: 10,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#FFFFFF',
        fontFamily: getFontFamily(props.bodyFontId, 'body'),
        fontSize: 36,
        fontWeight: 400,
        lineHeight: 1.38,
        textAlign: 'center',
        textShadow: '0 2px 8px rgba(0,0,0,0.86)',
      }}
    >{props.summary}</div>
  </div>;
};
