import React, {useLayoutEffect, useRef} from 'react';
import {AbsoluteFill, continueRender, delayRender} from 'remotion';
import {MediaBlockRenderer} from './MediaBlockRenderer';
import {TextBlockRenderer} from './TextBlockRenderer';

export const SceneLayoutRenderer: React.FC<{layout: any; narrative: any; images: any[]; mediaBaseUrl?: string; copyVisible?: boolean; showMedia?: boolean; showText?: boolean; mediaStyle?: React.CSSProperties; transparentBackground?: boolean}> = ({layout, narrative, images, mediaBaseUrl, copyVisible = true, showMedia = true, showText = true, mediaStyle, transparentBackground = false}) => {
  const sceneRef = useRef<HTMLDivElement>(null);
  const auditHandle = useRef<number | null>(null);
  if (auditHandle.current === null) auditHandle.current = delayRender(`Audit layout ${layout.layout_id ?? layout.scene_id}`);
  const content = new Map<string, Record<string, string>>((narrative?.contents ?? []).map((item: any) => [item.content_id, item]));
  useLayoutEffect(() => {
    const handle = auditHandle.current!;
    (async () => {
      await document.fonts.ready;
      const root = sceneRef.current;
      if (!root) { continueRender(handle); return; }
      const canvas = root.getBoundingClientRect();
      const blocks = Array.from(root.querySelectorAll<HTMLElement>('[data-layout-block]')).map((element) => {
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return {id: element.dataset.layoutBlock, fontId: element.dataset.fontId ?? null, x: rect.x - canvas.x, y: rect.y - canvas.y, width: rect.width, height: rect.height, scrollWidth: element.scrollWidth, clientWidth: element.clientWidth, scrollHeight: element.scrollHeight, clientHeight: element.clientHeight, fontFamily: style.fontFamily, textContent: element.textContent ?? ''};
      });
      console.error(`[LAYOUT_AUDIT]${JSON.stringify({layoutId: layout.layout_id, sceneId: layout.scene_id, fontsReady: document.fonts.status === 'loaded', blocks})}`);
      continueRender(handle);
    })().catch((error) => { console.error('[LAYOUT_AUDIT_ERROR]', error); continueRender(handle); });
  }, [layout.layout_id, layout.scene_id]);
  return <AbsoluteFill ref={sceneRef} style={{background: transparentBackground ? 'transparent' : layout.background.color}} data-layout-scene={layout.scene_id}>
    {showMedia && layout.media_blocks.map((block: any) => <MediaBlockRenderer key={block.block_id} block={block} asset={images.find((image) => image.id === block.asset_id)} mediaBaseUrl={mediaBaseUrl} frameStyle={mediaStyle}/>) }
    {showText && copyVisible && layout.text_blocks.map((block: any) => <TextBlockRenderer key={block.block_id} block={block} content={content.get(block.content_id)?.[block.variant_id] ?? ''}/>) }
  </AbsoluteFill>;
};
