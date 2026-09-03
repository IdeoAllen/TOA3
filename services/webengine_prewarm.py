# -*- coding: utf-8 -*-
"""Qt WebEngine 辅助。

注意：禁止把 QWebEngineView 长期挂在 MainShell/centralWidget 上「消闪」——
与业务页内嵌 View 并存时，Windows 上顶栏（引擎/业务/系统）来回切会原生闪退。
"""
from __future__ import annotations

import logging

logger = logging.getLogger("TOA3.webengine_prewarm")

_WARMED = False
_HOLD: list = []


def chromium_warmed() -> bool:
    return _WARMED


def bind_webengine_to_shell(shell) -> bool:
    """已废弃：勿锚定主壳。保留空实现以免旧调用炸掉。"""
    logger.debug("bind_webengine_to_shell 已禁用（防切页闪退）")
    return False


def prewarm_chromium_process(parent=None) -> bool:
    """可选：独立顶层离屏窗拉起进程，不挂主壳。"""
    global _WARMED
    if _WARMED:
        return True
    try:
        from PySide6.QtCore import Qt, QUrl
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWidgets import QApplication, QWidget
    except Exception:
        return False
    app = QApplication.instance()
    if app is None:
        return False
    try:
        holder = QWidget(None)
        holder.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        holder.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        holder.resize(8, 8)
        view = QWebEngineView(holder)
        view.setUrl(QUrl("about:blank"))
        holder.show()
        _ = view.winId()
        app.processEvents()
        _HOLD.append(holder)
        _WARMED = True
        logger.info("WebEngine 进程已离屏预热（未挂主壳）")
        return True
    except Exception:
        logger.debug("离屏预热失败", exc_info=True)
        return False


def cover_shell_for_webengine(shell, *, ms: int = 180) -> None:
    """空实现：遮罩挡不住整窗闪，且曾与切页冲突。"""
    return


def release_prewarm_hold() -> None:
    global _HOLD
    for w in _HOLD:
        try:
            w.hide()
            w.deleteLater()
        except Exception:
            pass
    _HOLD = []
