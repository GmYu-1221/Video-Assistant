"""Static validation for model-generated, deterministic animation documents."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup, NavigableString, Tag


class AnimationHTMLValidationError(ValueError):
    pass


_JS_TOKEN = re.compile(
    r'''(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`|//[^\n]*|/\*.*?\*/|[A-Za-z_$][\w$]*|(?:\d+\.\d*|\.\d+|\d+)|===|!==|=>|==|!=|<=|>=|\+\+|--|&&|\|\||\?\?|\?\.|\S)''',
    re.S,
)


_BANNED_PATTERNS = {
    "remote URL": r"(?:https?:)?//",
    "fetch": r"\bfetch\s*\(",
    "XMLHttpRequest": r"\bXMLHttpRequest\b",
    "WebSocket": r"\bWebSocket\b",
    "EventSource": r"\bEventSource\b",
    "dynamic import": r"\bimport\s*\(",
    "eval": r"\beval\s*\(",
    "Function constructor": r"\bnew\s+(?-i:Function)\b|\b(?:window\.)?(?-i:Function)\s*\(",
    "setTimeout": r"\bsetTimeout\b",
    "setInterval": r"\bsetInterval\b",
    "requestAnimationFrame": r"\brequestAnimationFrame\b",
    "Date.now": r"\bDate\.now\b",
    "performance.now": r"\bperformance\.now\b",
    "Math.random": r"\bMath\.random\b",
    "CSS animation": r"(?:^|[;{])\s*animation(?:-[\w-]+)?\s*:",
    "CSS keyframes": r"@keyframes\b",
    "CSS transition": r"(?:^|[;{])\s*transition(?:-[\w-]+)?\s*:",
}


def extract_complete_html(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:html)?\s*|\s*```$", "", cleaned, flags=re.I).strip()
    start = re.search(r"<!doctype\s+html", cleaned, re.I)
    end = cleaned.lower().rfind("</html>")
    if not start or end < start.start():
        raise AnimationHTMLValidationError("Animation Agent must return one complete HTML document")
    html = cleaned[start.start():end + len("</html>")]
    if cleaned[:start.start()].strip() or cleaned[end + len("</html>"):].strip():
        raise AnimationHTMLValidationError("Unexpected content outside the HTML document")
    return html


def validate_animation_html_repair_scope(original_html: str, repaired_html: str, contract_error: str) -> None:
    """Reject HTML repair changes outside code directly related to the error."""
    if _document_signature(original_html) != _document_signature(repaired_html):
        raise AnimationHTMLValidationError(
            "HTML Contract repair changed DOM structure, CSS, text, layout attributes, or material references"
        )
    if contract_error.startswith("A paused GSAP masterTimeline is required"):
        if _master_timeline_code_signature(original_html) != _master_timeline_code_signature(repaired_html):
            raise AnimationHTMLValidationError(
                "HTML Contract repair changed code outside masterTimeline declaration, alias removal, or directly related references"
            )
    elif _gsap_animation_signature(original_html) != _gsap_animation_signature(repaired_html):
        raise AnimationHTMLValidationError(
            "HTML Contract repair changed GSAP animation parameters or timeline positions"
        )


def _document_signature(html: str):
    soup = BeautifulSoup(html, "html.parser")

    def node_signature(node):
        if isinstance(node, NavigableString):
            text = " ".join(str(node).split())
            return ("text", text) if text else None
        if not isinstance(node, Tag):
            return None
        attrs = tuple(sorted(
            (key, tuple(value) if isinstance(value, list) else str(value))
            for key, value in node.attrs.items()
        ))
        if node.name == "script" and not node.get("src"):
            return ("script", attrs, "inline-script")
        if node.name == "style":
            css = re.sub(r"\s+", " ", node.get_text()).strip()
            return ("style", attrs, css)
        children = tuple(
            signature for child in node.children
            if (signature := node_signature(child)) is not None
        )
        return (node.name, attrs, children)

    return tuple(
        signature for child in soup.contents
        if (signature := node_signature(child)) is not None
    )


def _inline_script_tokens(html: str) -> list[list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    return [_JS_TOKEN.findall(tag.string or tag.get_text()) for tag in soup.find_all("script") if not tag.get("src")]


def _master_timeline_code_signature(html: str) -> tuple[tuple[str, ...], ...]:
    signatures = []
    for tokens in _inline_script_tokens(html):
        alias = "masterTimeline"
        for index in range(len(tokens) - 6):
            if (
                tokens[index] in {"const", "let", "var"}
                and re.fullmatch(r"[A-Za-z_$][\w$]*", tokens[index + 1])
                and tokens[index + 2:index + 7] == ["=", "gsap", ".", "timeline", "("]
            ):
                alias = tokens[index + 1]
                break
        normalized = ["masterTimeline" if token == alias else token for token in tokens]
        index = 0
        without_bridge = []
        while index < len(normalized):
            bridge = ["window", ".", "masterTimeline", "=", "masterTimeline"]
            if normalized[index:index + len(bridge)] == bridge:
                index += len(bridge)
                if index < len(normalized) and normalized[index] == ";":
                    index += 1
            else:
                without_bridge.append(normalized[index])
                index += 1
        signatures.append(tuple(without_bridge))
    return tuple(signatures)


def _gsap_animation_signature(html: str) -> tuple[tuple[str, ...], ...]:
    calls = []
    for tokens in _inline_script_tokens(html):
        index = 0
        while index + 2 < len(tokens):
            if tokens[index] == "." and tokens[index + 1] in {"to", "from", "fromTo", "set"} and tokens[index + 2] == "(":
                depth = 0
                end = index + 2
                while end < len(tokens):
                    if tokens[end] == "(":
                        depth += 1
                    elif tokens[end] == ")":
                        depth -= 1
                        if depth == 0:
                            break
                    end += 1
                calls.append(tuple(tokens[index:end + 1]))
                index = end
            index += 1
    return tuple(calls)


def _javascript_function_body(html: str, signature: re.Pattern[str]) -> str | None:
    """Extract a JS function body while ignoring braces in strings/comments."""
    match = signature.search(html)
    if not match:
        return None
    opening = html.find("{", match.end())
    if opening < 0:
        return None
    depth = 1
    index = opening + 1
    quote: str | None = None
    escaped = False
    line_comment = False
    block_comment = False
    while index < len(html):
        current = html[index]
        following = html[index + 1] if index + 1 < len(html) else ""
        if line_comment:
            if current in "\r\n":
                line_comment = False
        elif block_comment:
            if current == "*" and following == "/":
                block_comment = False
                index += 1
        elif quote:
            if escaped:
                escaped = False
            elif current == "\\":
                escaped = True
            elif current == quote:
                quote = None
        elif current == "/" and following == "/":
            line_comment = True
            index += 1
        elif current == "/" and following == "*":
            block_comment = True
            index += 1
        elif current in {"'", '"', "`"}:
            quote = current
        elif current == "{":
            depth += 1
        elif current == "}":
            depth -= 1
            if depth == 0:
                return html[opening + 1:index]
        index += 1
    return None


def _assigned_expression(body: str, identifier: str) -> str | None:
    match = re.search(
        rf"(?:const|let|var)\s+{re.escape(identifier)}\s*=\s*([^;\n]+)",
        body,
        re.I,
    )
    return match.group(1).strip() if match else None


def _is_meta_fps_expression(expression: str, body: str) -> bool:
    if re.search(r"window\s*\.\s*__ANIMATION_META__\s*\.\s*fps\b", expression, re.I):
        return True
    identifiers = re.findall(r"\b[A-Za-z_$][\w$]*\b", expression)
    return any(
        identifier.lower() == "fps"
        and (assigned := _assigned_expression(body, identifier)) is not None
        and re.search(r"window\s*\.\s*__ANIMATION_META__\s*\.\s*fps\b", assigned, re.I)
        for identifier in identifiers
    )


def _is_frame_time_expression(expression: str, body: str) -> bool:
    expression = expression.strip()
    if re.fullmatch(r"[A-Za-z_$][\w$]*", expression):
        assigned = _assigned_expression(body, expression)
        if assigned is None:
            return False
        expression = assigned
    return (
        bool(re.search(r"\bframe\b", expression, re.I))
        and "/" in expression
        and _is_meta_fps_expression(expression, body)
    )


def _validate_frame_timeline_seek(html: str) -> None:
    signature = re.compile(
        r"window\.renderFrame\s*=\s*async\s+function\s*\(\s*frame\s*\)",
        re.I,
    )
    body = _javascript_function_body(html, signature)
    if body is None:
        raise AnimationHTMLValidationError("Missing runtime contract: window.renderFrame")
    call = re.search(
        r"masterTimeline\.time\s*\(\s*([^,]+?)\s*,\s*false\s*\)",
        body,
        re.I | re.S,
    )
    if call and _is_frame_time_expression(call.group(1), body):
        return
    if re.search(r"masterTimeline\.seek\s*\(", body, re.I):
        detail = "found masterTimeline.seek(); use masterTimeline.time(frameTime, false)"
    elif re.search(r"masterTimeline\.time\s*\(", body, re.I):
        detail = "masterTimeline.time() must use frame/fps and pass false"
    else:
        detail = "renderFrame must seek masterTimeline with frame/fps"
    raise AnimationHTMLValidationError(f"Missing runtime contract: frame timeline seek ({detail})")


def validate_animation_html(html: str, project_dir: str | Path, *, width: int, height: int, fps: int, duration_frames: int) -> None:
    project = Path(project_dir).resolve()
    lowered = html.lower()
    for label, pattern in _BANNED_PATTERNS.items():
        if re.search(pattern, html, re.I | re.M):
            raise AnimationHTMLValidationError(f"Forbidden animation feature: {label}")
    soup = BeautifulSoup(html, "html.parser")
    if soup.find(["iframe", "object", "embed"]):
        raise AnimationHTMLValidationError("iframe, object and embed are forbidden")
    scripts = soup.find_all("script")
    if not any(tag.get("src") == "runtime/gsap.min.js" for tag in scripts):
        raise AnimationHTMLValidationError("GSAP must be loaded from runtime/gsap.min.js")
    if not re.search(r"(?:const|let|var)\s+masterTimeline\s*=\s*gsap\.timeline\s*\(\s*\{[^}]*paused\s*:\s*true", html, re.I | re.S):
        raise AnimationHTMLValidationError(
            "A paused GSAP masterTimeline is required: declare const masterTimeline = gsap.timeline({paused: true}); aliases such as window.masterTimeline = tl are not accepted"
        )
    if len(re.findall(r"\bgsap\.timeline\s*\(", html)) != 1:
        raise AnimationHTMLValidationError("Exactly one GSAP timeline is allowed")
    if re.search(r"\bmasterTimeline\.(?:play|resume|restart)\s*\(", html):
        raise AnimationHTMLValidationError("The master timeline must never auto-play")
    required = {
        "window.renderFrame": r"window\.renderFrame\s*=\s*async\s+function\s*\(\s*frame\s*\)",
        "window.__ANIMATION_READY__": r"window\.__ANIMATION_READY__\s*=\s*true",
        "window.__ANIMATION_META__": r"window\.__ANIMATION_META__\s*=\s*\{",
        "font readiness": r"document\.fonts\.ready",
    }
    for label, pattern in required.items():
        if not re.search(pattern, html, re.I | re.S):
            raise AnimationHTMLValidationError(f"Missing runtime contract: {label}")
    _validate_frame_timeline_seek(html)
    expected_meta = {
        "width": width, "height": height, "fps": fps, "durationFrames": duration_frames,
    }
    for key, expected in expected_meta.items():
        if not re.search(rf"\b{re.escape(key)}\s*:\s*{expected}\b", html):
            raise AnimationHTMLValidationError(f"Animation meta {key} must equal {expected}")

    for tag in soup.find_all(True):
        for attribute in ("src", "href", "poster"):
            value = tag.get(attribute)
            if value:
                _validate_local_reference(str(value), project)
        if tag.get("srcset"):
            raise AnimationHTMLValidationError("srcset is not allowed")
    for match in re.finditer(r"url\(\s*['\"]?([^)'\"]+)", html, re.I):
        _validate_local_reference(match.group(1), project)


def _validate_local_reference(value: str, project: Path) -> None:
    decoded = unquote(value.strip())
    if not decoded or decoded.startswith("#"):
        return
    parsed = urlsplit(decoded)
    if parsed.scheme or parsed.netloc or decoded.startswith(("/", "\\")):
        raise AnimationHTMLValidationError(f"Only project-relative resources are allowed: {value}")
    candidate = (project / parsed.path).resolve()
    try:
        relative = candidate.relative_to(project)
    except ValueError as exc:
        raise AnimationHTMLValidationError(f"Resource escapes project directory: {value}") from exc
    if not relative.parts or relative.parts[0] not in {"materials", "runtime", "background"}:
        raise AnimationHTMLValidationError(f"Resource is outside the allowlist: {value}")
    if not candidate.is_file():
        raise AnimationHTMLValidationError(f"Local resource does not exist: {value}")
