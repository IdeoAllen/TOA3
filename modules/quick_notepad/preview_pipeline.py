# -*- coding: utf-8 -*-
"""记事预览统一入口：普通 MD / Mermaid WebEngine · 大文档节流。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from PySide6.QtCore import QTimer, QUrl

from modules.quick_notepad.mermaid_preview import (
    build_reading_document_html,
    mermaid_js_path,
)
from modules.quick_notepad.rich_body import render_markdown_string

# 超此字节数节流预览，避免 UI 线程卡死（对齐 DartBin 超大 md 提示）
LARGE_DOC_BYTES = 200_000
LARGE_DOC_LINES = 4_000
PREVIEW_DEBOUNCE_MS = 350


@dataclass
class PreviewResult:
    kind: str  # "qt" | "web" | "empty"
    large: bool = False
    message: str = ""


class PreviewController:
    """页面级预览控制器：统一刷新 + 大文档防抖。"""

    def __init__(
        self,
        *,
        get_source_text: Callable[[], str],
        qt_preview: Any,
        preview_host: Any,
        ensure_web: Callable[[], Any],
        on_large: Callable[[str], None] | None = None,
        parent: Any = None,
    ) -> None:
        self._get_text = get_source_text
        self._qt_preview = qt_preview
        self._preview_host = preview_host
        self._ensure_web = ensure_web
        self._on_large = on_large
        self._timer = QTimer(parent)
        self._timer.setSingleShot(True)
        self._timer.setInterval(PREVIEW_DEBOUNCE_MS)
        self._timer.timeout.connect(self._flush)
        self._pending_force = False
        self._last_result = PreviewResult(kind="empty")

    @property
    def last_result(self) -> PreviewResult:
        return self._last_result

    def request_refresh(self, *, force: bool = False) -> None:
        """force=True 立即刷新（切 Tab）；否则大文档走防抖。"""
        md = self._get_text() or ""
        large = _is_large_doc(md)
        if force or not large:
            self._timer.stop()
            self._pending_force = False
            self._last_result = apply_preview(
                md,
                qt_preview=self._qt_preview,
                preview_host=self._preview_host,
                ensure_web=self._ensure_web,
            )
            if large and self._on_large:
                self._on_large("文档较大，预览已完整渲染")
            return
        self._pending_force = False
        if self._on_large:
            self._on_large("文档较大，预览已延迟…")
        self._timer.start()

    def _flush(self) -> None:
        md = self._get_text() or ""
        self._last_result = apply_preview(
            md,
            qt_preview=self._qt_preview,
            preview_host=self._preview_host,
            ensure_web=self._ensure_web,
        )
        if self._on_large and _is_large_doc(md):
            self._on_large("文档较大，预览已更新")


def _is_large_doc(md: str) -> bool:
    raw = md or ""
    if len(raw.encode("utf-8", errors="ignore")) >= LARGE_DOC_BYTES:
        return True
    return raw.count("\n") >= LARGE_DOC_LINES


def apply_preview(
    md: str,
    *,
    qt_preview: Any,
    preview_host: Any,
    ensure_web: Callable[[], Any],
) -> PreviewResult:
    """单一预览入口：能用 WebEngine 时一律纸面阅读态；否则退回 Qt Markdown。"""
    text = md or ""
    large = _is_large_doc(text)
    web = ensure_web() if text.strip() or preview_host is not None else None
    if not text.strip():
        qt_preview.blockSignals(True)
        try:
            qt_preview.clear()
        finally:
            qt_preview.blockSignals(False)
        if web is not None:
            _show_reading_html("", web, preview_host)
            return PreviewResult(kind="web", large=False)
        if preview_host is not None:
            preview_host.setCurrentWidget(qt_preview)
        return PreviewResult(kind="empty", large=False)

    # Qt 副本留给断言与无 WebEngine 时的回退；用户看见的是纸面。
    render_markdown_string(text, qt_preview)
    if web is not None:
        _show_reading_html(text, web, preview_host)
        return PreviewResult(kind="web", large=large)
    if preview_host is not None:
        preview_host.setCurrentWidget(qt_preview)
    return PreviewResult(kind="qt", large=large)


def _show_reading_html(md: str, web: Any, preview_host: Any) -> None:
    base_dir = mermaid_js_path().parent.resolve()
    html = build_reading_document_html(md)
    web.setHtml(html, QUrl.fromLocalFile(str(base_dir) + "/"))
    if preview_host is not None:
        preview_host.setCurrentWidget(web)


def scroll_preview_to_source_line(preview: Any, source_line: int, source_text: str) -> None:
    """按源码行号粗略滚到预览位置（Tab 切换场景，非像素双栏同步）。"""
    if preview is None or source_line < 0:
        return
    lines = (source_text or "").splitlines() or [""]
    line = min(max(0, source_line), len(lines) - 1)
    # 取光标附近非空行作锚点
    anchor = ""
    for i in range(line, -1, -1):
        piece = (lines[i] or "").strip().lstrip("#").strip()
        # 去掉常见 MD 前缀
        for prefix in ("- [x] ", "- [ ] ", "- [X] ", "- ", "* ", "> ", "```"):
            if piece.startswith(prefix):
                piece = piece[len(prefix) :].strip()
                break
        if piece and not piece.startswith("```"):
            anchor = piece[:48]
            break
    doc = getattr(preview, "document", lambda: None)()
    if doc is None:
        return
    if anchor:
        found = doc.find(anchor)
        if not found.isNull():
            preview.setTextCursor(found)
            preview.ensureCursorVisible()
            return
    # 回退：按行比例滚
    bar = preview.verticalScrollBar() if hasattr(preview, "verticalScrollBar") else None
    if bar is None:
        return
    total = max(1, len(lines) - 1)
    ratio = line / total
    bar.setValue(int(bar.minimum() + (bar.maximum() - bar.minimum()) * ratio))
