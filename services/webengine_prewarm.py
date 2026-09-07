# -*- coding: utf-8 -*-
"""Qt WebEngine 辅助。

注意：禁止把 QWebEngineView 长期挂在 MainShell/centralWidget 上「消闪」——
与业务页内嵌 View 并存时，Windows 上顶栏（引擎/业务/系统）来回切会原生闪退。

预热第二份 View 已禁用：与真内嵌并存会抖窗/闪烁。
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
    """已禁用：第二份离屏 View 与真内嵌并存会抖窗/闪烁。

    共享 WebEngine 首次 acquire 时自然拉起 Chromium 即可。
    """
    global _WARMED
    _WARMED = True
    release_prewarm_hold()
    logger.debug("prewarm_chromium_process 已禁用（防双 Chromium 闪烁）")
    return True


def cover_shell_for_webengine(shell, *, ms: int = 180) -> None:
    """空实现：遮罩挡不住整窗闪，且曾与切页冲突。"""
    return


def release_prewarm_hold() -> None:
    global _HOLD
    if not _HOLD:
        return
    for w in list(_HOLD):
        try:
            w.hide()
        except Exception:
            pass
        try:
            w.deleteLater()
        except Exception:
            pass
    _HOLD = []
    logger.debug("已释放 WebEngine 预热占位")
