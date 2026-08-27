# -*- coding: utf-8 -*-
"""正式版 / 开发版运行时隔离：避免全局热键、单实例互抢。"""
from __future__ import annotations

import os
import sys
from typing import List, Tuple

from services.runtime_paths import is_frozen

_RELEASE_EXE_NAMES = frozenset({"toa3.exe", "toa.exe"})


def list_release_toa_pids(exclude_pid: int | None = None) -> List[int]:
    """枚举本机正在运行的正式版 TOA/TOA3.exe PID（不含当前进程）。"""
    if sys.platform != "win32":
        return []
    me = int(exclude_pid if exclude_pid is not None else os.getpid())
    found: List[int] = []
    try:
        import ctypes
        from ctypes import wintypes

        TH32CS_SNAPPROCESS = 0x00000002

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260),
            ]

        kernel32 = ctypes.windll.kernel32
        snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snap in (-1, 0, 0xFFFFFFFF):
            return []
        try:
            pe = PROCESSENTRY32W()
            pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            if not kernel32.Process32FirstW(snap, ctypes.byref(pe)):
                return []
            while True:
                pid = int(pe.th32ProcessID)
                name = (pe.szExeFile or "").lower()
                if pid != me and name in _RELEASE_EXE_NAMES:
                    found.append(pid)
                if not kernel32.Process32NextW(snap, ctypes.byref(pe)):
                    break
        finally:
            kernel32.CloseHandle(snap)
    except Exception:
        return []
    return found


def release_toa_running() -> bool:
    return bool(list_release_toa_pids())


def instance_key() -> str:
    """单实例 QLocalServer 键：开发版与正式版分离。"""
    return "TOA3_YCZH_RELEASE" if is_frozen() else "TOA3_YCZH_DEV"


def app_mutex_name() -> str:
    """Inno AppMutex 名称（与 toa3_setup.iss 对齐）。"""
    return "YCZH_TOA3_RELEASE_MUTEX" if is_frozen() else "YCZH_TOA3_DEV_MUTEX"


def should_register_global_hotkeys() -> Tuple[bool, str]:
    if is_frozen():
        return True, "正式版占用全局热键"
    if release_toa_running():
        return (
            False,
            "正式版运行中：开发版已停用全局热键",
        )
    return True, "开发版独占全局热键"


def should_handle_global_hotkey_now() -> bool:
    ok, _ = should_register_global_hotkeys()
    return ok
