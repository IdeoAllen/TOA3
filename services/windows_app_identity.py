# -*- coding: utf-8 -*-
"""Windows 任务栏身份：避免 python -m 显示为「Python」且右键无实质动作。"""
from __future__ import annotations

import logging
import sys

logger = logging.getLogger("TOA3.winid")

# 与安装包 / 单实例锁同族，勿随意改（影响任务栏分组与跳转列表）
APP_USER_MODEL_ID = "YCZH.TOA3"


def apply_windows_app_identity(*, display_name: str = "运营宝 TOA3") -> None:
    """须在创建 QApplication 之前调用。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        logger.debug("SetCurrentProcessExplicitAppUserModelID failed", exc_info=True)

    # 显示名供部分壳层/无障碍读取；任务栏标题仍可能跟 exe，见 shell 窗标题
    try:
        import ctypes

        # SetProcessDpiAwareness 等无关；此处仅记 display 供后续 Qt 使用
        _ = display_name
    except Exception:
        pass


def wire_taskbar_activate(shell) -> None:
    """任务栏点击 / 系统「激活应用」时：若主窗藏在托盘则恢复。"""
    if shell is None:
        return
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return

    def _on_state(state) -> None:
        from PySide6.QtCore import Qt

        if state != Qt.ApplicationState.ApplicationActive:
            return
        try:
            # 仅恢复「藏进托盘」的主窗；已可见时不要抢焦点
            if not shell.isVisible():
                show = getattr(shell, "_show_from_tray", None)
                if callable(show):
                    show()
                else:
                    shell.showNormal()
                    shell.raise_()
                    shell.activateWindow()
        except Exception:
            logger.debug("taskbar activate restore failed", exc_info=True)

    # 避免重复连接
    if getattr(shell, "_toa_taskbar_activate_wired", False):
        return
    shell._toa_taskbar_activate_wired = True
    app.applicationStateChanged.connect(_on_state)
