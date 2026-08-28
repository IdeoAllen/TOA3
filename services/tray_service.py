# -*- coding: utf-8 -*-
"""系统托盘（QSystemTrayIcon · menu_registry 动态菜单）。"""
from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtGui import QAction, QCursor
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from services.icon_registry import app_window_icon
from services.notify_bus import register_tray_handler
from services.tray_menu import TrayMenuEntry

logger = logging.getLogger("TOA3.tray")


class TrayService:
    def __init__(self) -> None:
        self._tray: QSystemTrayIcon | None = None
        self._menu: QMenu | None = None
        self._on_show: Callable[[], None] | None = None
        self._on_restart: Callable[[], None] | None = None
        self._on_exit: Callable[[], None] | None = None
        self._has_update = False

    def start(
        self,
        *,
        on_show: Callable[[], None] | None = None,
        on_restart: Callable[[], None] | None = None,
        on_exit: Callable[[], None] | None = None,
        tip: str = "运营宝 TOA3",
    ) -> bool:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("系统托盘不可用")
            return False
        self._on_show = on_show
        self._on_restart = on_restart
        self._on_exit = on_exit
        icon = app_window_icon()
        if icon.isNull():
            icon = QApplication.windowIcon()
        tray = QSystemTrayIcon(icon)
        self._menu = QMenu()
        tray.setContextMenu(self._menu)
        tray.setToolTip(self._base_tip(tip))
        tray.activated.connect(self._on_activated)
        tray.show()
        self._tray = tray
        self._tip_base = tip

        def _balloon(title: str = "", body: str = "", level: str = "info", **_kw) -> None:
            if self._tray is None:
                return
            self._tray.showMessage(title or "TOA", body or "", self._tray.icon(), 4000)

        register_tray_handler(_balloon)
        return True

    def _base_tip(self, tip: str) -> str:
        extra = []
        if self._has_update:
            extra.append("有新版本")
        suffix = f" · {' · '.join(extra)}" if extra else ""
        return f"{tip}{suffix} · 双击打开 · 右键菜单"

    def rebuild_menu(
        self,
        entries: list[TrayMenuEntry],
        *,
        has_update: bool = False,
        on_check_update: Callable[[], None] | None = None,
        on_open_license: Callable[[], None] | None = None,
    ) -> None:
        if self._menu is None:
            return
        self._has_update = bool(has_update)
        menu = self._menu
        menu.clear()

        act_show = QAction("显示主窗口")
        if self._on_show:
            act_show.triggered.connect(self._on_show)
        menu.addAction(act_show)

        if entries:
            menu.addSeparator()
            for ent in entries:
                label = ent.title
                if ent.shortcut:
                    label = f"{label}\t{ent.shortcut}"
                act = QAction(label)
                if ent.summon:
                    act.triggered.connect(ent.summon)
                menu.addAction(act)

        menu.addSeparator()
        upd_label = "检查更新…" if has_update else "检查更新"
        if on_check_update:
            act_upd = QAction(upd_label)
            act_upd.triggered.connect(on_check_update)
            menu.addAction(act_upd)
        if on_open_license:
            act_lic = QAction("授权与订阅")
            act_lic.triggered.connect(on_open_license)
            menu.addAction(act_lic)

        menu.addSeparator()
        if self._on_restart:
            act_restart = QAction("重启")
            act_restart.triggered.connect(self._on_restart)
            menu.addAction(act_restart)
        act_exit = QAction("退出")
        if self._on_exit:
            act_exit.triggered.connect(self._on_exit)
        else:
            act_exit.triggered.connect(QApplication.instance().quit)
        menu.addAction(act_exit)

        if self._tray is not None:
            self._tray.setContextMenu(menu)
            self._tray.setToolTip(self._base_tip(getattr(self, "_tip_base", "TOA3")))

    def _popup_menu(self) -> None:
        if self._menu is None:
            return
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
