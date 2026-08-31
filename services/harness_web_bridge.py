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


def js_select_workspace(*, title: str = "", path: str = "") -> str:
    """展开侧栏工作区（只点带 aria-expanded 的 treeitem，避免误点会话）。"""
    t = (title or "").strip()
    p = (path or "").strip().replace("\\", "/")
    leaf = p.rsplit("/", 1)[-1] if p else ""
    return (
        "(function(){"
        f"const title={_js_str(t)};"
        f"const pathHint={_js_str(leaf or p)};"
        "const needles=[];"
        "if(title)needles.push(title.toLowerCase());"
        "if(pathHint)needles.push(pathHint.toLowerCase());"
        "if(!needles.length)return 'no_hint';"
        "const rows=[];"
        "for(const el of document.querySelectorAll('[role=\"treeitem\"][aria-expanded]')){"
        "const txt=(el.textContent||'').trim();"
        "if(!txt||txt.length>120)continue;"
        "const low=txt.toLowerCase();"
        "let score=99;"
        "for(const n of needles){"
        "if(!n)continue;"
        "if(low===n||low.startsWith(n))score=Math.min(score,0);"
        "else if(low.includes(n))score=Math.min(score,1);"
        "}"
        "if(score<99)rows.push({el,score,len:txt.length,exp:el.getAttribute('aria-expanded')});"
        "}"
        "rows.sort((a,b)=>a.score-b.score||a.len-b.len);"
        "if(!rows.length)return 'not_found';"
        "const hit=rows[0];"
        "if(hit.exp==='false'){try{hit.el.click();return 'expanded';}catch(e){return 'click_fail';}}"
        "return 'already_open';"
        "})();"
    )


def js_click_new_chat() -> str:
    """点击「新会话 / 新对话」。"""
    return (
        "(function(){"
        "function clickEl(el){try{el.click();return true;}catch(e){return false;}}"
        "const needles=['新会话','新对话','new chat','new session'];"
        "const scopes=[document.querySelector('nav'),document.querySelector('aside'),"
        "document.querySelector('[class*=\"sidebar\" i]'),document.body];"
        "for(const scope of scopes){if(!scope)continue;"
        "for(const el of scope.querySelectorAll('button,[role=\"button\"],a')){"
        "const txt=(el.textContent||'').trim().toLowerCase();"
        "if(!txt||txt.length>40)continue;"
        "for(const n of needles){if(txt.includes(n.toLowerCase())){if(clickEl(el))return 'clicked';}}"
        "}}"
        "return 'not_found';})();"
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


def select_workspace(
    view: Any,
    *,
    title: str = "",
    path: str = "",
    on_result: Callable[[str], None] | None = None,
) -> None:
    if view is None:
        return
    script = js_select_workspace(title=title, path=path)
    if on_result is not None:
        run_javascript(view, script, lambda r: on_result(str(r or "")))
    else:
        run_javascript(view, script)


def click_new_chat(
    view: Any,
    on_result: Callable[[str], None] | None = None,
) -> None:
    if view is None:
        return
    script = js_click_new_chat()
    if on_result is not None:
        run_javascript(view, script, lambda r: on_result(str(r or "")))
    else:
        run_javascript(view, script)


def js_select_session(*, session_id: str = "", title: str = "") -> str:
    """点选侧栏会话 treeitem（跳过工作区行）。"""
    sid = (session_id or "").strip()
    short = sid.replace("session-", "")[:8].lower() if sid else ""
    t = (title or "").strip()
    return (
        "(function(){"
        f"const short={_js_str(short)};"
        f"const title={_js_str(t)};"
        "const needles=[];"
        "if(title)needles.push(title.toLowerCase());"
        "if(short)needles.push(short);"
        "if(!needles.length)return 'no_hint';"
        "const rows=[];"
        "for(const el of document.querySelectorAll('[role=\"treeitem\"]')){"
        "if(el.hasAttribute('aria-expanded'))continue;"
        "const txt=(el.textContent||'').trim();"
        "if(!txt||txt.length>120)continue;"
        "const low=txt.toLowerCase();"
        "let score=99;"
        "for(const n of needles){"
        "if(!n)continue;"
        "if(low===n||low.startsWith(n))score=Math.min(score,0);"
        "else if(low.includes(n))score=Math.min(score,1);"
        "}"
        "if(score<99)rows.push({el,score,len:txt.length,sel:el.getAttribute('aria-selected')});"
        "}"
        "rows.sort((a,b)=>a.score-b.score||a.len-b.len);"
        "if(!rows.length)return 'not_found';"
        "const hit=rows[0];"
        "if(hit.sel==='true')return 'already_selected';"
        "try{hit.el.click();return 'clicked';}catch(e){return 'click_fail';}"
        "})();"
    )


def js_focus_workspace_session(
    *,
    workspace_title: str = "",
    workspace_path: str = "",
    session_id: str = "",
    session_title: str = "",
) -> str:
    """一步：展开工作区 → 点选会话。"""
    leaf = (workspace_path or "").strip().replace("\\", "/")
    leaf = leaf.rsplit("/", 1)[-1] if leaf else ""
    short = (session_id or "").replace("session-", "")[:8].lower()
    return (
        "(function(){"
        f"const wsTitle={_js_str((workspace_title or '').strip())};"
        f"const pathHint={_js_str(leaf)};"
        f"const sessTitle={_js_str((session_title or '').strip())};"
        f"const short={_js_str(short)};"
        "function expandWs(){"
        "const needles=[];"
        "if(wsTitle)needles.push(wsTitle.toLowerCase());"
        "if(pathHint)needles.push(pathHint.toLowerCase());"
        "if(!needles.length)return 'ws_no_hint';"
        "const rows=[];"
        "for(const el of document.querySelectorAll('[role=\"treeitem\"][aria-expanded]')){"
        "const txt=(el.textContent||'').trim();"
        "if(!txt||txt.length>120)continue;"
        "const low=txt.toLowerCase();"
        "let score=99;"
        "for(const n of needles){"
        "if(!n)continue;"
        "if(low===n||low.startsWith(n))score=Math.min(score,0);"
        "else if(low.includes(n))score=Math.min(score,1);"
        "}"
        "if(score<99)rows.push({el,score,len:txt.length,exp:el.getAttribute('aria-expanded')});"
        "}"
        "rows.sort((a,b)=>a.score-b.score||a.len-b.len);"
        "if(!rows.length)return 'ws_not_found';"
        "const hit=rows[0];"
        "if(hit.exp==='false'){try{hit.el.click();return 'ws_expanded';}catch(e){return 'ws_fail';}}"
        "return 'ws_open';"
        "}"
        "function openSess(){"
        "const needles=[];"
        "if(sessTitle)needles.push(sessTitle.toLowerCase());"
        "if(short)needles.push(short);"
        "if(!needles.length)return 'sess_no_hint';"
        "const rows=[];"
        "for(const el of document.querySelectorAll('[role=\"treeitem\"]')){"
        "if(el.hasAttribute('aria-expanded'))continue;"
        "const txt=(el.textContent||'').trim();"
        "if(!txt||txt.length>120)continue;"
        "const low=txt.toLowerCase();"
        "let score=99;"
        "for(const n of needles){"
        "if(!n)continue;"
        "if(low===n||low.startsWith(n))score=Math.min(score,0);"
        "else if(low.includes(n))score=Math.min(score,1);"
        "}"
        "if(score<99)rows.push({el,score,len:txt.length,sel:el.getAttribute('aria-selected')});"
        "}"
        "rows.sort((a,b)=>a.score-b.score||a.len-b.len);"
        "if(!rows.length)return 'sess_not_found';"
        "const hit=rows[0];"
        "if(hit.sel==='true')return 'sess_selected';"
        "try{hit.el.click();return 'sess_clicked';}catch(e){return 'sess_fail';}"
        "}"
        "return expandWs()+'|'+openSess();"
        "})();"
    )


def select_session(
    view: Any,
    *,
    session_id: str = "",
    title: str = "",
    on_result: Callable[[str], None] | None = None,
) -> None:
    if view is None:
        return
    script = js_select_session(session_id=session_id, title=title)
    if on_result is not None:
        run_javascript(view, script, lambda r: on_result(str(r or "")))
    else:
        run_javascript(view, script)


def focus_extension_session(
    view: Any,
    *,
    workspace_title: str,
    workspace_path: str,
    session_id: str = "",
    session_title: str = "",
    on_done: Callable[[str], None] | None = None,
    retries: int = 8,
    retry_ms: int = 650,
) -> None:
    """展开工作区 → 点选会话；侧栏晚到时自动重试。"""
    if view is None:
        if on_done:
            on_done("no_view")
        return

    from PySide6.QtCore import QTimer

    attempt = {"n": 0}

    def _attempt() -> None:
        attempt["n"] += 1
        script = js_focus_workspace_session(
            workspace_title=workspace_title,
            workspace_path=workspace_path,
            session_id=session_id,
            session_title=session_title,
        )

        def _after(r: str) -> None:
            summary = str(r or "")
            sess_ok = ("sess_clicked" in summary) or ("sess_selected" in summary)
            just_expanded = "ws_expanded" in summary
            # 展开后会话节点可能下一拍才出现；或 SSE 尚未推到侧栏
            if (not sess_ok or just_expanded) and attempt["n"] < max(1, retries):
                if just_expanded and sess_ok and attempt["n"] >= 2:
                    if on_done:
                        on_done(summary)
                    return
                if just_expanded or not sess_ok:
                    QTimer.singleShot(max(200, int(retry_ms)), _attempt)
                    return
            if on_done:
                on_done(summary if summary else "done")

        run_javascript(view, script, _after)

    QTimer.singleShot(400, _attempt)


def prepare_extension_session(
    view: Any,
    *,
    title: str,
    path: str,
    prompt: str,
    on_done: Callable[[str], None] | None = None,
) -> None:
    """工作区 →（短延时）新会话 →（短延时）填入任务。"""
    if view is None:
        if on_done:
            on_done("no_view")
        return

    from PySide6.QtCore import QTimer

    steps: list[str] = []

    def _finish() -> None:
        if on_done:
            on_done("|".join(steps) if steps else "done")

    def _after_inject(r: str) -> None:
        steps.append(f"inject:{r}")
        _finish()

    def _do_inject() -> None:
        inject_prompt(view, prompt, on_result=_after_inject)

    def _after_chat(r: str) -> None:
        steps.append(f"chat:{r}")
        QTimer.singleShot(350, _do_inject)

    def _do_chat() -> None:
        click_new_chat(view, on_result=_after_chat)

    def _after_ws(r: str) -> None:
        steps.append(f"ws:{r}")
        QTimer.singleShot(400, _do_chat)

    select_workspace(view, title=title, path=path, on_result=_after_ws)
