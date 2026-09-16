# -*- coding: utf-8 -*-
"""后台剪贴板监听：文本 / 原图复制即入库。"""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QGuiApplication

from modules.clipboard_history.history_store import (
    privacy_on as store_privacy_on,
    push_clipboard_image,
    push_text,
    set_privacy as store_set_privacy,
)

logger = logging.getLogger("TOA3.clipboard")


class ClipboardWatcher(QObject):
    captured = Signal(str)
    privacy_changed = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._last_text = ""
        self._last_image_sig = ""
        self._suppress = False
        self._enabled = True
        cb = QGuiApplication.clipboard()
        if cb is not None:
            cb.dataChanged.connect(self._on_changed)

    def set_enabled(self, on: bool) -> None:
        self._enabled = bool(on)

    def set_privacy(self, on: bool) -> None:
        """隐私时段：暂停入库（投屏开会用）；状态持久化。"""
        prev = store_privacy_on()
        store_set_privacy(on)
        if bool(on) != prev:
            self.privacy_changed.emit(bool(on))

    def privacy_on(self) -> bool:
        return store_privacy_on()

    def suppress_once(self) -> None:
        self._suppress = True

    def _on_changed(self) -> None:
        if not self._enabled or store_privacy_on():
            return
        if self._suppress:
            self._suppress = False
            return
        cb = QGuiApplication.clipboard()
        if cb is None:
            return

        text = (cb.text() or "").strip()
        if text and text != self._last_text:
            self._last_text = text
            entry = push_text(text, source="auto")
            if entry:
                self.captured.emit(str(entry.get("id") or ""))
                logger.debug("clipboard text %s chars", len(text))
            return

        # 有文本时不抢图（Word 等图文混合）
        if text:
            return

        mime = cb.mimeData()
        sig = ""
        if mime is not None:
            for fmt in ("image/png", "image/jpeg", "image/bmp", "image/webp"):
                if mime.hasFormat(fmt):
                    raw = mime.data(fmt)
                    data = bytes(raw.data()) if hasattr(raw, "data") else bytes(raw)
                    sig = f"{fmt}:{len(data)}"
                    break
            if not sig and mime.hasImage():
                img = mime.imageData()
                if img is not None and hasattr(img, "width"):
                    sig = f"qimage:{img.width()}x{img.height()}"
        if not sig:
            pix = cb.pixmap()
            if pix is None or pix.isNull():
                return
            sig = f"pixmap:{pix.width()}x{pix.height()}:{pix.cacheKey()}"
        if sig == self._last_image_sig:
            return
        self._last_image_sig = sig
        entry = push_clipboard_image(cb, source="auto")
        if entry:
            self.captured.emit(str(entry.get("id") or ""))
            logger.debug(
                "clipboard image original %sx%s",
                entry.get("width"),
                entry.get("height"),
            )


_WATCHER: ClipboardWatcher | None = None


def get_clipboard_watcher() -> ClipboardWatcher:
    global _WATCHER
    if _WATCHER is None:
        _WATCHER = ClipboardWatcher()
    return _WATCHER
