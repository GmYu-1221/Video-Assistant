"""Post-layout validation in Chromium.

Pillow can be used by callers as a cheap preflight, but this module is the
layout truth: browser font loading and DOM geometry decide whether text fits.
"""
from __future__ import annotations

from html import escape
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import quote

from content_creator.font_registry import get_registered_font, load_font_registry
from content_creator.schemas import LayoutIssue, RenderedLayoutValidationResult, SceneLayoutSpec, SceneNarrative
from .validator import intersects


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def copyfile(self, source, outputfile):
        try:
            super().copyfile(source, outputfile)
        except (BrokenPipeError, ConnectionResetError):
            pass


def _font_server(root: Path):
    handler = lambda *args, **kwargs: _QuietHandler(*args, directory=str(root), **kwargs)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    Thread(target=server.serve_forever, daemon=True).start()
    return server


def validate_rendered_layout(spec: SceneLayoutSpec, narrative: SceneNarrative, remotion_public: str | Path) -> RenderedLayoutValidationResult:
    """Measure a LayoutPreview-equivalent DOM after document.fonts.ready."""
    content = {item.content_id: item for item in narrative.contents}
    public = Path(remotion_public)
    server = _font_server(public)
    port = server.server_address[1]
    blocks = [*spec.media_blocks, *spec.text_blocks]
    html_blocks = []
    required_fonts: dict[str, dict] = {}
    selected_fonts: dict[str, dict] = {}
    for block in spec.text_blocks:
        font = get_registered_font(block.font_id)
        required_fonts[font["id"]] = font
        selected_fonts[font["id"]] = font
        fallback = next((candidate for candidate in load_font_registry() if candidate["family"] == font["fallback_family"]), None)
        if fallback:
            required_fonts[fallback["id"]] = dict(fallback)
        value = escape(content[block.content_id].value(block.variant_id))
        html_blocks.append(f'<div data-layout-block="{block.block_id}" data-font-id="{font["id"]}" style="position:absolute;left:{block.bbox.x}px;top:{block.bbox.y}px;width:{block.bbox.width}px;height:{block.bbox.height}px;overflow:visible;overflow-wrap:anywhere;word-break:break-word;font-family:&quot;{font["family"]}&quot;,&quot;{font["fallback_family"]}&quot;;font-size:{ {"display":72,"headline":54,"body":36,"caption":30,"metadata":26,"quote":44,"numeric":60}[block.typography_role.value] }px;line-height:1.28;white-space:pre-wrap">{value}</div>')
    for block in spec.media_blocks:
        html_blocks.append(f'<div data-layout-block="{block.block_id}" style="position:absolute;left:{block.bbox.x}px;top:{block.bbox.y}px;width:{block.bbox.width}px;height:{block.bbox.height}px"></div>')
    font_faces = "".join(f'@font-face{{font-family:"{font["family"]}";src:url("http://127.0.0.1:{port}/{quote(font["local_path"], safe="/")}");font-weight:{font["weights"][0]};font-display:block}}' for font in required_fonts.values())
    html = f'''<!doctype html><style>{font_faces}#canvas{{position:relative;width:1080px;height:1920px;overflow:hidden}}</style><div id="canvas">{''.join(html_blocks)}</div>'''
    issues: list[LayoutIssue] = []
    details: dict[str, dict] = {}
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
            page.set_content(html, wait_until="load")
            measured = page.evaluate("""async (families) => { await Promise.all(families.map((family)=>document.fonts.load(`16px "${family}"`))); await document.fonts.ready; const canvas=document.querySelector('#canvas').getBoundingClientRect(); const blocks=[...document.querySelectorAll('[data-layout-block]')].map((el)=>{const r=el.getBoundingClientRect(); return {id:el.dataset.layoutBlock,fontId:el.dataset.fontId ?? null,x:r.x-canvas.x,y:r.y-canvas.y,width:r.width,height:r.height,scrollWidth:el.scrollWidth,clientWidth:el.clientWidth,scrollHeight:el.scrollHeight,clientHeight:el.clientHeight,font:getComputedStyle(el).fontFamily};}); return {fontLoaded:families.every((family)=>document.fonts.check(`16px "${family}"`)),blocks}; }""", [font["family"] for font in selected_fonts.values()])
            browser.close()
        for item in measured["blocks"]:
            details[item["id"]] = item
            if item["x"] < 0 or item["y"] < 0 or item["x"] + item["width"] > 1080 or item["y"] + item["height"] > 1920:
                issues.append(LayoutIssue(code="rendered_canvas_bounds", block_id=item["id"], message="Chromium measured block outside canvas"))
            if item["scrollWidth"] > item["clientWidth"] + 1 or item["scrollHeight"] > item["clientHeight"] + 1:
                issues.append(LayoutIssue(code="rendered_overflow", block_id=item["id"], message="Chromium measured text overflow"))
        for index, left in enumerate(blocks):
            for right in blocks[index + 1:]:
                if intersects(left.bbox, right.bbox) and frozenset((left.block_id, right.block_id)) not in {frozenset(pair) for pair in spec.overlay_policy.allowed_pairs}:
                    issues.append(LayoutIssue(code="rendered_collision", block_id=right.block_id, message="Chromium preview contains undeclared collision"))
        if not measured["fontLoaded"]:
            issues.append(LayoutIssue(code="font_not_loaded", severity="critical", message="Chromium did not load every selected registered font"))
        return RenderedLayoutValidationResult(scene_id=spec.scene_id, fonts_ready=bool(measured["fontLoaded"]), font_families=[font["family"] for font in selected_fonts.values()], blocks=details, issues=issues, passed=not issues)
    except Exception as exc:
        issues.append(LayoutIssue(code="rendered_validation_unavailable", severity="critical", message=f"Chromium rendered validation failed: {exc}"))
        return RenderedLayoutValidationResult(scene_id=spec.scene_id, issues=issues, passed=False)
    finally:
        server.shutdown()
