# -*- coding: utf-8 -*-
"""平台体验编排：托盘 · 更新 · 授权 Chip · 启动检查。"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer

from core.status_service import StatusLevel
from services.notify_bus import get_bus
from services.update_check import UpdateCheckResult, format_up_to_date_message, get_update_hub
from services.tray_menu import build_tray_menu_model
from services.tray_service import get_tray

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
        try:
            from services.windows_app_identity import wire_taskbar_activate

            wire_taskbar_activate(shell)
        except Exception:
            logger.debug("wire_taskbar_activate failed", exc_info=True)
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
            from services.user_plan_presentation import OFFICIAL_TIER_LABEL, TRIAL_TIER_LABEL

            days = lm.get_remaining_days()
            if days == float("inf") or int(days) > 7:
                return

            shell = self._shell
            if shell is None:
                return

            ent = lm.get_entitlement()
            if lm.is_standalone_mode():
                body = (
                    f"{TRIAL_TIER_LABEL}将于 {int(days)} 天后到期，"
                    f"请授权码登录或购买{OFFICIAL_TIER_LABEL}。"
                )
            elif not lm.is_licensed():
                return
            elif ent == "trial":
                body = f"试用授权将于 {int(days)} 天后到期，请升级{OFFICIAL_TIER_LABEL}。"
            elif ent == "paid":
                body = f"{OFFICIAL_TIER_LABEL}将于 {int(days)} 天后到期，请在此续费。"
            else:
                body = f"授权将于 {int(days)} 天后到期，请查看续费选项。"

            get_tray().show_message(shell._st.brand_name(), body)
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

        model = build_tray_menu_model(
            summon_module=shell._summon_module,
            screenshot_region=lambda: run_screenshot_hotkey(shell, full=False),
            screenshot_full=lambda: run_screenshot_hotkey(shell, full=True),
            open_clipboard=shell._open_clipboard_quick,
        )
        get_tray().rebuild_menu(
            model,
            has_update=bool(self._last_update and self._last_update.has_update),
            on_check_update=lambda: self.check_for_update(reason="tray"),
            on_open_settings=self._open_settings,
            on_open_expiry=self._open_expiry_action,
        )

    def _open_settings(self) -> None:
        shell = self._shell
        if shell is None:
            return
        shell.navigate("system_settings")

    def _open_expiry_action(self) -> None:
        shell = self._shell
        if shell is None:
            return
        from app.commerce_dialog import open_purchase_dialog

        open_purchase_dialog(shell, forced=False)

    def _open_license_settings(self) -> None:
        shell = self._shell
        if shell is None:
            return
        from services.settings_access import is_settings_admin

        if is_settings_admin():
            shell.navigate("system_settings")
            page = shell._pages.get("system_settings")
            if page is not None and hasattr(page, "open_license_or_subscription"):
                page.open_license_or_subscription()
            return
        from app.commerce_dialog import open_account_dialog

        open_account_dialog(shell)

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

        hub = get_update_hub()
        reason = hub.last_reason()

        if result.has_update:
            title = shell._st.brand_name()
            latest = result.latest_version or "新版本"
            body = f"发现新版本 v{latest}（当前 v{result.current_version}）"
            if result.below_min_version and result.min_version:
                body = (
                    f"版本过旧（低于 v{result.min_version}）· "
                    f"请升级到 v{latest}"
                )
            get_tray().show_message(title, body)
            if reason == "startup":
                shell.show_status(
                    f"有新版本 v{latest} · 托盘或关于页可下载",
                    level=StatusLevel.INFO,
                )
            elif reason == "tray":
                # 与关于/设置同路径：唤起主窗 + 专用更新对话框（可应用内下载）
                shell._show_from_tray()
                shell.show_status(
                    f"发现新版本 v{latest} · 请在对话框中下载或打开下载页",
                    level=StatusLevel.INFO,
                )
                from app.update_available_dialog import present_update_available

                QTimer.singleShot(
                    50,
                    lambda r=result, s=shell: present_update_available(s, r),
                )
            return

        # 关于页手动检查由 AboutDialog / AppUpdateSection 弹窗；托盘手动检查在此提示
        if reason == "tray" and not result.has_update:
            msg = format_up_to_date_message(result, for_tray=True)
            get_tray().show_message(shell._st.brand_name(), msg)

    def refresh_license_chip(self) -> None:
        shell = self._shell
        if shell is None or not hasattr(shell, "_license_chip"):
            return
        try:
            from services.user_plan_presentation import user_chip_display

            chip = shell._license_chip
            text, kind, tooltip = user_chip_display()
            chip.setText(text)
            chip.setProperty("class", f"msg-{kind}")
            chip.setToolTip(tooltip)
            chip.setMaximumWidth(96)
            chip.setFixedHeight(18)
            chip.style().unpolish(chip)
            chip.style().polish(chip)
            if hasattr(shell, "_refresh_status_plan_label"):
                shell._refresh_status_plan_label()
            if hasattr(shell, "_refresh_status_version_label"):
                shell._refresh_status_version_label()
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
