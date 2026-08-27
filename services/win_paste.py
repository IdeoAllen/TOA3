# -*- coding: utf-8 -*-
"""Windows：把剪贴板内容 Ctrl+V 到先前前台窗口（对标 Win+V 写回）。"""
from __future__ import annotations

import logging
import sys

logger = logging.getLogger("TOA3.win_paste")


def get_foreground_hwnd() -> int | None:
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        hwnd = int(ctypes.windll.user32.GetForegroundWindow() or 0)
        return hwnd or None
    except Exception:
        logger.debug("GetForegroundWindow failed", exc_info=True)
        return None


def restore_foreground(hwnd: int | None) -> bool:
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        user32.AllowSetForegroundWindow(0xFFFFFFFF)
        return bool(user32.SetForegroundWindow(int(hwnd)))
    except Exception:
        logger.debug("SetForegroundWindow failed", exc_info=True)
        return False


def send_ctrl_v() -> bool:
    """模拟 Ctrl+V。"""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        ULONG_PTR = ctypes.c_uint64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
        INPUT_KEYBOARD = 1
        KEYEVENTF_KEYUP = 0x0002
        VK_CONTROL = 0x11
        VK_V = 0x56

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = (
                ("wVk", ctypes.c_ushort),
                ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ULONG_PTR),
            )

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = (
                ("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ULONG_PTR),
            )

        class HARDWAREINPUT(ctypes.Structure):
            _fields_ = (
                ("uMsg", ctypes.c_ulong),
                ("wParamL", ctypes.c_short),
                ("wParamH", ctypes.c_ushort),
            )

        class INPUTUNION(ctypes.Union):
            _fields_ = (("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT))

        class INPUT(ctypes.Structure):
            _fields_ = (("type", ctypes.c_ulong), ("union", INPUTUNION))

        def _down(vk: int) -> INPUT:
            i = INPUT(type=INPUT_KEYBOARD)
            i.union.ki = KEYBDINPUT(vk, 0, 0, 0, 0)
            return i

        def _up(vk: int) -> INPUT:
            i = INPUT(type=INPUT_KEYBOARD)
            i.union.ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP, 0, 0)
            return i

        seq = (INPUT * 4)(_down(VK_CONTROL), _down(VK_V), _up(VK_V), _up(VK_CONTROL))
        sent = ctypes.windll.user32.SendInput(4, ctypes.byref(seq), ctypes.sizeof(INPUT))
        return int(sent) == 4
    except Exception:
        logger.debug("SendInput Ctrl+V failed", exc_info=True)
        return False


def paste_to_window(hwnd: int | None) -> None:
    """恢复前台窗口并 Ctrl+V（应在弹层关闭后短延迟调用）。"""
    restore_foreground(hwnd)
    send_ctrl_v()
