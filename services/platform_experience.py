# -*- coding: utf-8 -*-
"""平台体验编排：托盘 · 更新 · 授权 Chip · 启动检查。"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer

from core.status_service import StatusLevel
from services.notify_bus import get_bus
from services.tray_menu import build_tray_entries
from services.tray_service import get_tray
from services.update_check import UpdateCheckResult, get_update_hub

if TYPE_CHECKING:
    from app.shell import MainShell

logger = logging.getLogger("TOA3.platform")


class PlatformExperience(QObject):
    def __init__(self) -> None:
        super().__init__()
        self._shell: MainShell | None = None
        self._last_update: UpdateCheckResult | None = None
        hub = get_update_hub()
        hub.result_ready.connect(self._on_update_result)
        hub.checking_changed.connect(self._on_checking_changed)

    def attach_shell(self, shell: MainShell) -> None:
        self._shell = shell
        self._start_tray()
        self.refresh_license_chip()
        bus = get_bus()
        bus.license_changed.connect(self.refresh_license_chip)
        bus.license_changed.connect(self._rebuild_tray_menu)
        bus.nav_rebuild_requested.connect(self._rebuild_tray_menu)
        cfg = self._update_cfg()
        if cfg.get("check_on_startup", True) is not False:
            QTimer.singleShot(2500, lambda: self.check_for_update(reason="startup"))
        QTimer.singleShot(3500, self._maybe_license_tray_hint)

    def _maybe_license_tray_hint(self) -> None:
        try:
            from services.license_manager import global_license_manager as lm

            if lm.is_standalone_mode() or not lm.is_licensed():
                return
            days = lm.get_remaining_days()
            if days == float("inf") or days > 7:
                return
            shell = self._shell
            if shell is None:
                return
            get_tray().show_message(
                shell._st.brand_name(),
                f"授权将于 {int(days)} 天后到期，请前往「授权与订阅」续费。",
            )
        except Exception:
            pass

    def _update_cfg(self) -> dict:
        try:
            from services.config_service import get_update_config

            return get_update_config()
        except Exception:
            return {}

    def _start_tray(self) -> None:
        shell = self._shell
        if shell is None:
            return
        tray = get_tray()
        tray.start(
            tip=f"{shell._st.brand_name()} TOA3",
            on_show=shell._show_from_tray,
            on_restart=shell._restart_app,
            on_exit=shell._quit_app,
        )
        self._rebuild_tray_menu()

    def _rebuild_tray_menu(self) -> None:
        shell = self._shell
        if shell is None:
            return
        from services.screenshot_service import run_screenshot_hotkey

        entries = build_tray_entries(
            summon_module=shell._summon_module,
            screenshot_region=lambda: run_screenshot_hotkey(shell, full=False),
            screenshot_full=lambda: run_screenshot_hotkey(shell, full=True),
            open_clipboard=shell._open_clipboard_quick,
        )
        get_tray().rebuild_menu(
            entries,
            has_update=bool(self._last_update and self._last_update.has_update),
            on_check_update=lambda: self.check_for_update(reason="tray"),
            on_open_license=self._open_license_settings,
        )

    def _open_license_settings(self) -> None:
        shell = self._shell
        if shell is None:
            return
        shell.navigate("system_settings")
        page = shell._pages.get("system_settings")
        if page is not None and hasattr(page, "open_license_or_subscription"):
            page.open_license_or_subscription()

    def check_for_update(self, *, reason: str = "manual") -> None:
        hub = get_update_hub()
        if hub.is_checking():
            return
        hub.check_async(reason=reason)

    def _on_checking_changed(self, busy: bool) -> None:
        # AboutAppSection 已直接订阅 UpdateCheckHub
        pass

    def _on_update_result(self, result: object) -> None:
        if not isinstance(result, UpdateCheckResult):
            return
        self._last_update = result
        self._rebuild_tray_menu()
        shell = self._shell
        if shell is None:
            return

        if result.has_update and result.latest_version:
            title = shell._st.brand_name()
            body = f"发现新版本 v{result.latest_version}（当前 v{result.current_version}）"
            get_tray().show_message(title, body)
            hub = get_update_hub()
            if hub.last_reason() == "startup":
                shell.show_status(
                    f"有新版本 v{result.latest_version} · 托盘或关于页可下载",
                    level=StatusLevel.INFO,
                )
            return

        hub = get_update_hub()
        # 关于页手动检查由 AboutAppSection 弹窗；托盘手动检查在此提示
        if hub.last_reason() == "tray" and not result.has_update:
            msg = f"当前版本 {result.current_version} 已是最新"
            if result.error:
                msg = result.error
            get_tray().show_message(shell._st.brand_name(), msg)

    def refresh_license_chip(self) -> None:
        shell = self._shell
        if shell is None or not hasattr(shell, "_license_chip"):
            return
        try:
            from services.license_manager import global_license_manager as lm

            chip = shell._license_chip
            if lm.is_standalone_mode():
                text, kind = "正式版", "warning"
            elif lm.is_licensed():
                days = lm.get_remaining_days()
                if days != float("inf") and days <= 7:
                    text, kind = f"续费 {int(days)}天", "warning"
                else:
                    text, kind = "已授权", "success"
            else:
                text, kind = "开通", "warning"
            chip.setText(text)
            chip.setProperty("class", f"msg-{kind}")
            chip.setToolTip(lm.get_validity_text())
            chip.style().unpolish(chip)
            chip.style().polish(chip)
        except Exception:
            pass

    def apply_close_to_tray(self) -> None:
        shell = self._shell
        if shell is None:
            return
        from services.config_service import get_hotkeys_config

        shell._close_to_tray = bool(get_hotkeys_config().get("close_to_background", True))


_PLATFORM: PlatformExperience | None = None


def get_platform_experience() -> PlatformExperience:
    global _PLATFORM
    if _PLATFORM is None:
        _PLATFORM = PlatformExperience()
    return _PLATFORM
