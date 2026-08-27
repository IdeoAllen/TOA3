# -*- coding: utf-8 -*-
"""全局热键（Windows RegisterHotKey）；非 Windows 回退为空操作。"""
from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QAbstractNativeEventFilter, QByteArray, QObject, QTimer

logger = logging.getLogger("TOA3.hotkey")

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
WM_HOTKEY = 0x0312


def _parse_hotkey(spec: str) -> tuple[int, int] | None:
    """'Alt+A' / 'Ctrl+Shift+A' -> (modifiers, vk)."""
    parts = [p.strip().lower() for p in str(spec or "").split("+") if p.strip()]
    if not parts:
        return None
    key = parts[-1]
    mods = 0
    # 只用全名作修饰键，避免把键位字母 a/c/s 误当成 Alt/Ctrl/Shift
    for p in parts[:-1]:
        if p == "alt":
            mods |= MOD_ALT
        elif p in ("ctrl", "control"):
            mods |= MOD_CONTROL
        elif p == "shift":
            mods |= MOD_SHIFT
        elif p in ("win", "meta", "cmd"):
            mods |= MOD_WIN
    vk_map = {chr(c): c for c in range(ord("A"), ord("Z") + 1)}
    vk_map.update({str(i): 0x30 + i for i in range(10)})
    vk = vk_map.get(key.upper() if len(key) == 1 else key)
    if vk is None and len(key) == 1:
        vk = ord(key.upper())
    if vk is None:
        return None
    return mods, vk


class _HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, owner: "HotkeyService") -> None:
        super().__init__()
        self._owner = owner

    def nativeEventFilter(self, eventType, message):  # noqa: N802
        if sys.platform != "win32":
            return False, 0
        try:
            import ctypes
            from ctypes import wintypes

            if bytes(eventType) not in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
                # PySide6 may pass QByteArray
                et = eventType.data() if hasattr(eventType, "data") else eventType
                if et not in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
                    return False, 0
            msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
            if msg.message == WM_HOTKEY:
                hid = int(msg.wParam)
                self._owner._on_hotkey(hid)
                return True, 0
        except Exception:
            logger.debug("hotkey filter error", exc_info=True)
        return False, 0


class HotkeyService(QObject):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._callbacks: dict[int, Callable[[], None]] = {}
        self._next_id = 1
        self._filter: _HotkeyFilter | None = None
        self._user32 = None

    def apply(self, bindings: dict[str, Callable[[], None]]) -> dict[str, str]:
        """bindings: hotkey_spec -> callback. 返回错误表。"""
        self.clear()
        errors: dict[str, str] = {}
        if sys.platform != "win32":
            return {k: "仅 Windows 支持全局热键" for k in bindings}

        import ctypes

        self._user32 = ctypes.windll.user32
        if self._filter is None:
            self._filter = _HotkeyFilter(self)
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is not None:
                app.installNativeEventFilter(self._filter)

        for spec, cb in bindings.items():
            parsed = _parse_hotkey(spec)
            if not parsed:
                errors[spec] = "无法解析热键"
                continue
            mods, vk = parsed
            hid = self._next_id
            self._next_id += 1
            ok = self._user32.RegisterHotKey(None, hid, mods, vk)
            if not ok:
                errors[spec] = "RegisterHotKey 失败（可能被占用）"
                continue
            self._callbacks[hid] = cb
        return errors

    def _on_hotkey(self, hid: int) -> None:
        try:
            from services.edition_isolation import should_handle_global_hotkey_now

            if not should_handle_global_hotkey_now():
                return
        except Exception:
            pass
        cb = self._callbacks.get(hid)
        if cb:
            QTimer.singleShot(0, cb)

    def clear(self) -> None:
        if self._user32 is not None:
            for hid in list(self._callbacks.keys()):
                try:
                    self._user32.UnregisterHotKey(None, hid)
                except Exception:
                    pass
        self._callbacks.clear()

    def shutdown(self) -> None:
        self.clear()
        if self._filter is not None:
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is not None:
                app.removeNativeEventFilter(self._filter)
            self._filter = None


_HK: HotkeyService | None = None


def get_hotkey_service() -> HotkeyService:
    global _HK
    if _HK is None:
        _HK = HotkeyService()
    return _HK
