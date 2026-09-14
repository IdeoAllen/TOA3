# -*- coding: utf-8 -*-
"""全局双击 Ctrl 唤起主窗（RegisterHotKey 无法表达 Double+Ctrl）。"""
from __future__ import annotations

import ctypes
import logging
import sys
import time
from ctypes import wintypes
from typing import Callable

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger("TOA3.hotkey.double_ctrl")

WH_KEYBOARD_LL = 13
WM_KEYUP = 0x0101
WM_SYSKEYUP = 0x0105
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
_DOUBLE_CTRL_INTERVAL_S = 0.55
_FIRE_DEBOUNCE_S = 0.45


def is_double_ctrl_spec(spec: str) -> bool:
    raw = str(spec or "").strip().lower().replace(" ", "")
    return raw in {"double+ctrl", "ctrl+ctrl", "doublectrl", "2xctrl"}


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class DoubleCtrlSummonService(QObject):
    """低级别键盘钩子；用 Signal 回到 GUI 线程执行唤起。"""

    summon_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._hook_id = None
        self._proc = None
        self._last_ctrl_up = 0.0
        self._last_ctrl_down = 0.0
        self._last_fire = 0.0
        self._user32 = None

    def apply(self, callback: Callable[[], None] | None) -> str:
        self.stop()
        if callback is None or sys.platform != "win32":
            return ""
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            try:
                self.summon_requested.disconnect()
            except (TypeError, RuntimeError):
                pass
        self.summon_requested.connect(callback)

        self._user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        @ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        def _hook_proc(n_code, w_param, l_param):
            if n_code >= 0:
                kb = ctypes.cast(l_param, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
                is_up = int(w_param) in (WM_KEYUP, WM_SYSKEYUP)
                self._on_key(int(kb.vkCode), is_up)
            if self._hook_id:
                return self._user32.CallNextHookEx(self._hook_id, n_code, w_param, l_param)
            return 0

        self._proc = _hook_proc
        # WH_KEYBOARD_LL：hMod 在本进程钩子应为 NULL。PyInstaller 冻结包里
        # GetModuleHandleW(None) 常失败 → 双击 Ctrl 整段不可用。
        hmods: list[object] = [None, 0]
        try:
            exe = getattr(sys, "executable", None)
            if exe:
                hmods.append(kernel32.GetModuleHandleW(str(exe)))
        except Exception:
            pass
        hmods.append(kernel32.GetModuleHandleW(None))

        self._hook_id = None
        last_err = 0
        for hmod in hmods:
            kernel32.SetLastError(0)
            hid = self._user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, hmod, 0)
            if hid:
                self._hook_id = hid
                break
            last_err = int(kernel32.GetLastError() or 0)
        if not self._hook_id:
            self._proc = None
            try:
                self.summon_requested.disconnect()
            except Exception:
                pass
            logger.warning("SetWindowsHookExW failed: %s", last_err)
            return f"双击 Ctrl 监听安装失败(err={last_err})"
        logger.info("double Ctrl summon hook installed")
        return ""

    def _fire(self) -> None:
        now = time.monotonic()
        if now - self._last_fire < _FIRE_DEBOUNCE_S:
            return
        self._last_fire = now
        self._last_ctrl_up = 0.0
        self._last_ctrl_down = 0.0
        try:
            from services.edition_isolation import should_handle_global_hotkey_now

            if not should_handle_global_hotkey_now():
                return
        except Exception:
            pass
        logger.debug("double Ctrl detected, requesting summon")
        self.summon_requested.emit()

    def _on_key(self, vk: int, is_up: bool) -> None:
        if vk not in (VK_LCONTROL, VK_RCONTROL):
            if not is_up:
                self._last_ctrl_up = 0.0
                self._last_ctrl_down = 0.0
            return
        now = time.monotonic()
        if is_up:
            self._last_ctrl_up = now
            return
        # 第二次按下：松开后按 或 连续两次按下
        if self._last_ctrl_up and (now - self._last_ctrl_up) <= _DOUBLE_CTRL_INTERVAL_S:
            self._fire()
            return
        if self._last_ctrl_down and (now - self._last_ctrl_down) <= _DOUBLE_CTRL_INTERVAL_S:
            self._fire()
            return
        self._last_ctrl_down = now

    def stop(self) -> None:
        if self._hook_id and self._user32 is not None:
            try:
                self._user32.UnhookWindowsHookEx(self._hook_id)
            except Exception:
                logger.debug("UnhookWindowsHookEx failed", exc_info=True)
        self._hook_id = None
        self._proc = None
        self._last_ctrl_up = 0.0
        self._last_ctrl_down = 0.0
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            try:
                self.summon_requested.disconnect()
            except (TypeError, RuntimeError):
                pass


_SERVICE: DoubleCtrlSummonService | None = None


def get_double_ctrl_summon() -> DoubleCtrlSummonService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = DoubleCtrlSummonService()
    return _SERVICE


def apply_double_ctrl_summon(shell) -> str:
    """按 enable_global_toggle 安装或卸载双击 Ctrl。"""
    from services.config_service import get_hotkeys_config
    from services.menu_registry import is_migrated
    from services.module_hotkeys import normalize_module_id

    svc = get_double_ctrl_summon()
    if shell is not None:
        svc.setParent(shell)

    hk = get_hotkeys_config()
    enabled = bool(hk.get("enable_global_toggle", True))
    if not enabled:
        svc.stop()
        return ""

    from services.edition_isolation import should_register_global_hotkeys

    ok, reason = should_register_global_hotkeys()
    if not ok:
        svc.stop()
        logger.info("跳过双击 Ctrl 注册: %s", reason)
        return ""

    summon_id = normalize_module_id(hk.get("summon_module_id"))
    show = getattr(shell, "_show_from_tray", None)
    summon = getattr(shell, "_summon_module", None)
    if not callable(show):
        svc.stop()
        return "主窗唤起不可用"

    def _on_double_ctrl() -> None:
        try:
            if summon_id and is_migrated(summon_id) and callable(summon):
                summon(summon_id)
            else:
                show()
        except Exception:
            logger.exception("double Ctrl summon failed")

    return svc.apply(_on_double_ctrl)
