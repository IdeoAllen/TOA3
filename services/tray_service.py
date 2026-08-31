# -*- coding: utf-8 -*-
"""系统托盘（QSystemTrayIcon · Figma T3 分组菜单）。"""
from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtGui import QAction, QFont, QKeySequence
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from services.icon_registry import app_window_icon
from services.notify_bus import register_tray_handler
from services.tray_menu import TrayMenuEntry, TrayMenuModel

logger = logging.getLogger("TOA3.tray")

_SECTION_SUMMON = "快捷唤起"
_SECTION_AUTH = "授权与更新"


class TrayService:
    def __init__(self) -> None:
        self._tray: QSystemTrayIcon | None = None
        self._menu: QMenu | None = None
        self._on_show: Callable[[], None] | None = None
        self._on_restart: Callable[[], None] | None = None
        self._on_exit: Callable[[], None] | None = None
        self._on_open_settings: Callable[[], None] | None = None
        self._on_open_expiry: Callable[[], None] | None = None
        self._has_update = False
        self._tip_base = "TOA3"

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
        tray.setToolTip(self._compose_tooltip(tip))
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

    def _compose_tooltip(self, brand_tip: str) -> str:
        try:
            from services.user_plan_presentation import user_status_plan_label

            plan_line = user_status_plan_label()
        except Exception:
            plan_line = ""
        parts = [brand_tip]
        if plan_line:
            parts.append(plan_line)
        if self._has_update:
            parts.append("有新版本")
        parts.append("双击打开")
        return " · ".join(parts)

    def rebuild_menu(
        self,
        model: TrayMenuModel,
        *,
        has_update: bool = False,
        on_check_update: Callable[[], None] | None = None,
        on_open_settings: Callable[[], None] | None = None,
        on_open_expiry: Callable[[], None] | None = None,
    ) -> None:
        if self._menu is None:
            return
        self._has_update = bool(has_update)
        self._on_open_settings = on_open_settings
        self._on_open_expiry = on_open_expiry
        menu = self._menu
        menu.clear()

        act_show = QAction("显示主窗口", menu)
        if self._on_show:
            act_show.triggered.connect(self._on_show)
        menu.addAction(act_show)

        if model.summon:
            menu.addSeparator()
            self._add_section_title(menu, _SECTION_SUMMON)
            for ent in model.summon:
                self._add_entry(menu, ent, indent=True)

        menu.addSeparator()
        self._add_section_title(menu, _SECTION_AUTH)
        status = QAction(f"  {model.license_line}", menu)
        status.setEnabled(False)
        menu.addAction(status)

        upd_label = "  检查更新…" if has_update else "  检查更新"
        if on_check_update:
            act_upd = QAction(upd_label, menu)
            act_upd.triggered.connect(on_check_update)
            menu.addAction(act_upd)

        if model.show_expiry_action and on_open_expiry:
            act_exp = QAction(f"  {model.expiry_label}", menu)
            act_exp.triggered.connect(on_open_expiry)
            menu.addAction(act_exp)

        menu.addSeparator()
        if on_open_settings:
            act_set = QAction("设置", menu)
            act_set.triggered.connect(on_open_settings)
            menu.addAction(act_set)
        if self._on_restart:
            act_restart = QAction("重启", menu)
            act_restart.triggered.connect(self._on_restart)
            menu.addAction(act_restart)
        act_exit = QAction("退出", menu)
        if self._on_exit:
            act_exit.triggered.connect(self._on_exit)
        else:
            act_exit.triggered.connect(QApplication.instance().quit)
        menu.addAction(act_exit)

        if self._tray is not None:
            self._tray.setContextMenu(menu)
            self._tray.setToolTip(self._compose_tooltip(getattr(self, "_tip_base", "TOA3")))

    @staticmethod
    def _add_section_title(menu: QMenu, title: str) -> None:
        if hasattr(menu, "addSection"):
            menu.addSection(title)
            return
        act = QAction(title, menu)
        act.setEnabled(False)
        font = QFont(act.font())
        font.setBold(True)
        act.setFont(font)
        menu.addAction(act)

    @staticmethod
    def _add_entry(menu: QMenu, ent: TrayMenuEntry, *, indent: bool = False) -> None:
        title = ent.title
        if indent:
            title = f"  {title}"
        # Windows 托盘菜单默认可能不画 setShortcut，用 Tab 把快捷键写进文案
        seq = str(ent.shortcut or "").strip()
        label = f"{title}\t{seq}" if seq else title
        act = QAction(label, menu)
        if seq:
            act.setShortcut(QKeySequence(seq))
            try:
                act.setShortcutVisibleInContextMenu(True)
            except Exception:
                pass
            act.setToolTip(f"{ent.title} ({seq})")
        if ent.summon:
            act.triggered.connect(ent.summon)
        menu.addAction(act)

    def _on_activated(self, reason) -> None:
        # 左键单击/双击均恢复主窗；右键仍走 setContextMenu
        if reason in (
            QSystemTrayIcon.ActivationReason.DoubleClick,
            QSystemTrayIcon.ActivationReason.Trigger,
        ) and self._on_show:
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
