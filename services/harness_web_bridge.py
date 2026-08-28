# -*- coding: utf-8 -*-
"""Harness WebEngine 桥：主题和谐、会话恢复、投喂注入。"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def _js_str(value: str) -> str:
    return json.dumps(value)


def build_harmonize_css(palette: dict[str, Any]) -> str:
    bg = str(palette.get("background") or "#1e1e1e")
    surface = str(palette.get("surface") or bg)
    border = str(palette.get("border_default") or "#333333")
    text = str(palette.get("text_primary") or "#cccccc")
    return (
        f"html, body {{ background: {bg} !important; color: {text} !important; }}"
        f"::-webkit-scrollbar-thumb {{ background: {border} !important; }}"
        f"::-webkit-scrollbar-track {{ background: {surface} !important; }}"
        "body { font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif !important; }"
    )


def js_try_resume_session(session_id: str, resume_uri: str) -> str:
    sid = session_id or ""
    uri = resume_uri or ""
    return (
        "(function(){"
        f"const fullId={_js_str(sid)};"
        f"const uri={_js_str(uri)};"
        "const short=fullId.replace(/^session-/,'').slice(0,8).toLowerCase();"
        "function clickEl(el){try{el.click();return true;}catch(e){return false;}}"
        "for(const el of document.querySelectorAll('[data-session-id],[data-sessionid],[data-id]')){"
        "const v=(el.getAttribute('data-session-id')||el.getAttribute('data-sessionid')||el.getAttribute('data-id')||'').toLowerCase();"
        "if(v&&((v===fullId.toLowerCase())||v.includes(short))){if(clickEl(el))return 'clicked_attr';}}"
        "const scopes=[document.querySelector('nav'),document.querySelector('aside'),"
        "document.querySelector('[class*=\"sidebar\" i]'),document.querySelector('[class*=\"Sidebar\"]'),document.body];"
        "for(const scope of scopes){if(!scope)continue;"
        "for(const el of scope.querySelectorAll('button,[role=\"button\"],li,div[tabindex],a')){"
        "const txt=(el.textContent||'').toLowerCase();"
        "if(short&&txt.includes(short)){if(clickEl(el))return 'clicked_sidebar';}}}"
        "const input=document.querySelector('textarea,[contenteditable=\"true\"],[role=\"textbox\"]');"
        "if(input&&uri){input.focus();"
        "if(input.tagName==='TEXTAREA'||input.tagName==='INPUT'){input.value=uri+' ';input.dispatchEvent(new Event('input',{bubbles:true}));}"
        "else{input.textContent=uri+' ';input.dispatchEvent(new InputEvent('input',{bubbles:true,data:uri}));}"
        "return 'uri_pasted';}"
        "return 'not_found';})();"
    )


def js_inject_prompt(text: str) -> str:
    body = _js_str(text)
    return (
        "(function(){"
        f"const text={body};"
        "const input=document.querySelector('textarea,[contenteditable=\"true\"],[role=\"textbox\"]');"
        "if(!input)return 'no_input';"
        "input.focus();"
        "if(input.tagName==='TEXTAREA'||input.tagName==='INPUT'){"
        "input.value=text;input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));}"
        "else{input.textContent=text;input.dispatchEvent(new InputEvent('input',{bubbles:true,data:text}));}"
        "return 'ok';})();"
    )


def run_javascript(
    view: Any,
    script: str,
    on_result: Callable[[Any], None] | None = None,
) -> None:
    if view is None:
        return
    page = view.page()
    if page is None:
        return
    if on_result is not None:
        page.runJavaScript(script, on_result)
    else:
        page.runJavaScript(script)


def apply_theme_harmonize(view: Any, palette: dict[str, Any]) -> None:
    if view is None or not palette:
        return
    css = build_harmonize_css(palette)
    escaped = json.dumps(css)
    run_javascript(view, f"(function(){{const id='toa3-harness-harmonize';"
                         f"let s=document.getElementById(id);"
                         f"if(!s){{s=document.createElement('style');s.id=id;document.head.appendChild(s);}}"
                         f"s.textContent={escaped};}})();")


def apply_readability_boost(view: Any) -> None:
    """内嵌 Web 字体抗锯齿与字号（不改 Harness 主题色）。"""
    if view is None:
        return
    css = (
        "html { -webkit-font-smoothing: antialiased !important; "
        "text-rendering: optimizeLegibility !important; }"
        "body, button, input, textarea { "
        "font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif !important; "
        "font-size: 15px !important; line-height: 1.55 !important; }"
        "code, pre { font-size: 14px !important; }"
    )
    escaped = json.dumps(css)
    run_javascript(
        view,
        f"(function(){{const id='toa3-harness-readability';"
        f"let s=document.getElementById(id);"
        f"if(!s){{s=document.createElement('style');s.id=id;document.head.appendChild(s);}}"
        f"s.textContent={escaped};}})();",
    )


def set_web_zoom(view: Any, factor: float) -> None:
    if view is None:
        return
    try:
        view.setZoomFactor(max(0.5, min(2.0, float(factor))))
    except (TypeError, ValueError, AttributeError):
        pass


def try_resume_session(
    view: Any,
    session_id: str,
    resume_uri: str,
    on_result: Callable[[str], None] | None = None,
) -> None:
    script = js_try_resume_session(session_id, resume_uri)
    if on_result is not None:
        run_javascript(view, script, lambda r: on_result(str(r or "not_found")))
    else:
        run_javascript(view, script)


def inject_prompt(
    view: Any,
    text: str,
    on_result: Callable[[str], None] | None = None,
) -> None:
    t = (text or "").strip()
    if not t:
        return
    script = js_inject_prompt(t)
    if on_result is not None:
        run_javascript(view, script, lambda r: on_result(str(r or "")))
    else:
        run_javascript(view, script)
