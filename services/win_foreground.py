# -*- coding: utf-8 -*-
"""Windows：把主窗从托盘/后台拉到前台（绕过 ForegroundLockTimeout）。"""
from __future__ import annotations

import logging
import sys

logger = logging.getLogger("TOA3.win_foreground")

SW_RESTORE = 9
ASFW_ANY = 0xFFFFFFFF


def force_widget_foreground(widget) -> bool:
    """尽量恢复可见并抢前台；非 Windows 回退 Qt API。"""
    if widget is None:
        return False
    try:
        if widget.isMinimized():
            widget.showNormal()
        elif not widget.isVisible():
            widget.show()
        else:
            widget.showNormal()
        widget.raise_()
        widget.activateWindow()
    except Exception:
        logger.debug("Qt show/activate failed", exc_info=True)

    if sys.platform != "win32":
        return bool(widget.isVisible())

    try:
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = int(widget.winId())
        if not hwnd:
            return bool(widget.isVisible())
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        user32.AllowSetForegroundWindow(ASFW_ANY)
        ok = bool(user32.SetForegroundWindow(hwnd))
        if not ok:
            user32.BringWindowToTop(hwnd)
        widget.raise_()
        widget.activateWindow()
        return ok or widget.isVisible()
    except Exception:
        logger.debug("SetForegroundWindow failed", exc_info=True)
        return bool(widget.isVisible())
