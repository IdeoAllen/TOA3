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
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312


def _parse_hotkey(spec: str) -> tuple[int, int] | None:
    """'Alt+A' / 'Ctrl+Shift+A' / 'F11' -> (modifiers, vk)."""
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
    # F1–F24
    if len(key) >= 2 and key[0] == "f" and key[1:].isdigit():
        n = int(key[1:])
        if 1 <= n <= 24:
            return mods, 0x70 + n - 1
    vk_map = {chr(c): c for c in range(ord("A"), ord("Z") + 1)}
    vk_map.update({str(i): 0x30 + i for i in range(10)})
    # 常用功能键
    vk_map.update(
        {
            "esc": 0x1B,
            "escape": 0x1B,
            "space": 0x20,
            "tab": 0x09,
            "enter": 0x0D,
            "return": 0x0D,
        }
    )
    vk = vk_map.get(key.upper() if len(key) == 1 else key)
    if vk is None and len(key) == 1:
        vk = ord(key.upper())
    if vk is None:
        return None
    return mods, vk


def _is_windows_msg_event(eventType) -> bool:
    raw_parts: list[bytes] = []
    if isinstance(eventType, QByteArray):
        raw_parts.append(bytes(eventType))
    elif isinstance(eventType, (bytes, bytearray, memoryview)):
        raw_parts.append(bytes(eventType))
    elif isinstance(eventType, str):
        raw_parts.append(eventType.encode("ascii", errors="ignore"))
    else:
        try:
            raw_parts.append(bytes(eventType))
        except Exception:
            if hasattr(eventType, "data"):
                try:
                    raw_parts.append(bytes(eventType.data()))
                except Exception:
                    pass
    for raw in raw_parts:
        low = raw.decode("ascii", errors="ignore").lower()
        if "windows" in low and "msg" in low:
            return True
    return False


def _message_address(message) -> int | None:
    if message is None:
        return None
    if isinstance(message, int):
        return message
    try:
        return int(message)
    except (TypeError, ValueError, OverflowError):
        pass
    try:
        from shiboken6 import Shiboken

        if Shiboken.isValid(message):
            return int(Shiboken.VoidPtr(message).toAddress())
    except Exception:
        pass
    try:
        import ctypes

        addr = ctypes.cast(message, ctypes.c_void_p).value
        if addr:
            return int(addr)
    except Exception:
        pass
    return None


class _HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, owner: "HotkeyService") -> None:
        super().__init__()
        self._owner = owner

    def nativeEventFilter(self, eventType, message):  # noqa: N802
        if sys.platform != "win32":
            return False, 0
        if not _is_windows_msg_event(eventType):
            return False, 0
        try:
            from ctypes import wintypes

            addr = _message_address(message)
            if not addr:
                return False, 0
            msg = wintypes.MSG.from_address(addr)
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
        self._specs: dict[int, str] = {}
        self._next_id = 1
        self._filter: _HotkeyFilter | None = None
        self._user32 = None

    def active_count(self) -> int:
        return len(self._callbacks)

    def active_specs(self) -> list[str]:
        return [self._specs[i] for i in sorted(self._specs) if i in self._callbacks]

    def apply(self, bindings: dict[str, Callable[[], None]]) -> dict[str, str]:
        """bindings: hotkey_spec -> callback. 返回错误表。"""
        self.clear()
        return self.register_many(bindings)

    def register_many(
        self,
        bindings: dict[str, Callable[[], None]],
        *,
        only_specs: set[str] | None = None,
    ) -> dict[str, str]:
        """增量注册（不清空已成功项）。only_specs 非空时只尝试这些键。"""
        errors: dict[str, str] = {}
        if sys.platform != "win32":
            targets = only_specs or set(bindings)
            return {k: "仅 Windows 支持全局热键" for k in targets}

        import ctypes

        self._user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        if self._filter is None:
            self._filter = _HotkeyFilter(self)
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is not None:
                app.installNativeEventFilter(self._filter)

        already = {str(s) for s in self._specs.values()}
        for spec, cb in bindings.items():
            key = str(spec)
            if only_specs is not None and key not in only_specs:
                continue
            if key in already:
                continue
            parsed = _parse_hotkey(key)
            if not parsed:
                errors[key] = "无法解析热键"
                continue
            mods, vk = parsed
            hid = self._next_id
            self._next_id += 1
            kernel32.SetLastError(0)
            ok = self._user32.RegisterHotKey(None, hid, mods | MOD_NOREPEAT, vk)
            if not ok:
                kernel32.SetLastError(0)
                ok = self._user32.RegisterHotKey(None, hid, mods, vk)
            if not ok:
                err = int(kernel32.GetLastError() or 0)
                if err == 1409:
                    errors[key] = "已被其它程序占用"
                elif err:
                    errors[key] = f"RegisterHotKey 失败(err={err})"
                else:
                    errors[key] = "RegisterHotKey 失败（可能被占用）"
                continue
            self._callbacks[hid] = cb
            self._specs[hid] = key
            already.add(key)
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
        self._specs.clear()

    def shutdown(self) -> None:
        self.clear()
        try:
            from services.double_ctrl_summon import get_double_ctrl_summon

            get_double_ctrl_summon().stop()
        except Exception:
            pass
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
