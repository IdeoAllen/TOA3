# -*- coding: utf-8 -*-
"""授权到期巡检：定期联网校验，失效后刷新菜单并提示。"""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QTimer

logger = logging.getLogger("TOA3.license_watchdog")

_INTERVAL_MS = 5 * 60 * 1000


class LicenseWatchdog(QObject):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setInterval(_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)
        self._was_licensed = False

    def start(self) -> None:
        try:
            from services.edition_profile import edition_id
            from services.license_manager import global_license_manager

            if edition_id() == "standalone" and global_license_manager.is_standalone_mode():
                logger.debug("license watchdog skipped (standalone local_free)")
                return
            self._was_licensed = bool(global_license_manager.is_licensed())
        except Exception:
            self._was_licensed = False
        self._timer.start()
        logger.debug("license watchdog started (%ss)", _INTERVAL_MS // 1000)

    def _tick(self) -> None:
        try:
            from services.license_manager import global_license_manager

            global_license_manager.invalidate_license_cache()
            licensed = bool(global_license_manager.is_licensed())
            if self._was_licensed and not licensed:
                msg = global_license_manager.reconcile_after_expiry()
                self._on_license_lost(msg)
            self._was_licensed = licensed
        except Exception as e:
            logger.warning("license watchdog tick failed: %s", e)

    def _on_license_lost(self, message: str) -> None:
        from PySide6.QtCore import QTimer

        from services.notify_bus import emit_license_changed

        emit_license_changed()
        parent = self.parent()
        if parent is not None:
            QTimer.singleShot(
                300,
                lambda: self._show_renew(parent, message),
            )
        logger.info("license expired: %s", message)

    def _show_renew(self, parent, message: str) -> None:
        try:
            from app.renew_dialog import offer_renew_dialog

            offer_renew_dialog(parent, message=message or "订阅已到期，续费后可继续使用。")
        except Exception as e:
            logger.warning("renew dialog failed: %s", e)


_WATCHDOG: LicenseWatchdog | None = None


def start_license_watchdog(parent=None) -> LicenseWatchdog:
    global _WATCHDOG
    if _WATCHDOG is None:
        _WATCHDOG = LicenseWatchdog(parent)
        _WATCHDOG.start()
    return _WATCHDOG
