# -*- coding: utf-8 -*-
"""系统托盘（QSystemTrayIcon）。"""
from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtGui import QAction, QCursor
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from services.icon_registry import app_window_icon
from services.notify_bus import register_tray_handler

logger = logging.getLogger("TOA3.tray")


class TrayService:
    def __init__(self) -> None:
        self._tray: QSystemTrayIcon | None = None
        self._menu: QMenu | None = None
        self._on_show: Callable[[], None] | None = None

    def start(
        self,
        *,
        on_show: Callable[[], None] | None = None,
        on_notepad: Callable[[], None] | None = None,
        on_pomodoro: Callable[[], None] | None = None,
        on_clipboard: Callable[[], None] | None = None,
        on_screenshot: Callable[[], None] | None = None,
        on_screenshot_full: Callable[[], None] | None = None,
        on_ocr: Callable[[], None] | None = None,
        on_harness: Callable[[], None] | None = None,
        on_restart: Callable[[], None] | None = None,
        on_exit: Callable[[], None] | None = None,
        tip: str = "运营宝 TOA3",
    ) -> bool:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("系统托盘不可用")
            return False
        self._on_show = on_show
        icon = app_window_icon()
        if icon.isNull():
            icon = QApplication.windowIcon()
        tray = QSystemTrayIcon(icon)
        menu = QMenu()
        act_show = QAction("显示主窗口")
        if on_show:
            act_show.triggered.connect(on_show)
        menu.addAction(act_show)
        if on_notepad:
            act = QAction("快速记事")
            act.triggered.connect(on_notepad)
            menu.addAction(act)
        if on_pomodoro:
            act = QAction("番茄钟")
            act.triggered.connect(on_pomodoro)
            menu.addAction(act)
        if on_clipboard:
            act = QAction("剪贴板历史")
            act.triggered.connect(on_clipboard)
            menu.addAction(act)
        if on_screenshot:
            act = QAction("区域截图")
            act.triggered.connect(on_screenshot)
            menu.addAction(act)
        if on_screenshot_full:
            act = QAction("全屏截图")
            act.triggered.connect(on_screenshot_full)
            menu.addAction(act)
        if on_ocr:
            act = QAction("截图转文字")
            act.triggered.connect(on_ocr)
            menu.addAction(act)
        if on_harness:
            act = QAction("编码智能体")
            act.triggered.connect(on_harness)
            menu.addAction(act)
        menu.addSeparator()
        if on_restart:
            act_restart = QAction("重启")
            act_restart.triggered.connect(on_restart)
            menu.addAction(act_restart)
        act_exit = QAction("退出")
        if on_exit:
            act_exit.triggered.connect(on_exit)
        else:
            act_exit.triggered.connect(QApplication.instance().quit)
        menu.addAction(act_exit)
        tray.setContextMenu(menu)
        tray.setToolTip(f"{tip} · 双击打开 · 右键退出")
        tray.activated.connect(self._on_activated)
        tray.show()
        self._tray = tray
        self._menu = menu

        def _balloon(title: str = "", body: str = "", level: str = "info", **_kw) -> None:
            if self._tray is None:
                return
            self._tray.showMessage(title or "TOA", body or "", self._tray.icon(), 4000)

        register_tray_handler(_balloon)
        return True

    def _popup_menu(self) -> None:
        if self._menu is None:
            return
        # Win11 溢出托盘区有时不弹出 setContextMenu，需手动 popup
        self._menu.popup(QCursor.pos())

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Context:
            self._popup_menu()
            return
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick and self._on_show:
            self._on_show()

    def show_message(self, title: str, body: str) -> None:
        if self._tray:
            self._tray.showMessage(title, body, self._tray.icon(), 4000)

    def stop(self) -> None:
        if self._tray:
            self._tray.hide()
            self._tray = None
        self._menu = None


_TRAY: TrayService | None = None


def get_tray() -> TrayService:
    global _TRAY
    if _TRAY is None:
        _TRAY = TrayService()
    return _TRAY
