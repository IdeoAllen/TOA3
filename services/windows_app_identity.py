# -*- coding: utf-8 -*-
"""Windows 任务栏身份：避免 python -m 显示为「Python」且右键无实质动作。"""
from __future__ import annotations

import logging
import os
import sys
from ctypes import (
    HRESULT,
    POINTER,
    Structure,
    byref,
    c_byte,
    c_size_t,
    c_ulong,
    c_ushort,
    c_void_p,
    c_wchar,
    cast,
    create_unicode_buffer,
    memmove,
    sizeof,
    windll,
)
from ctypes.wintypes import HWND
from typing import Any

logger = logging.getLogger("TOA3.winid")

# 与安装包 / 单实例锁同族，勿随意改（影响任务栏分组与跳转列表）
APP_USER_MODEL_ID = "YCZH.TOA3"
APP_USER_MODEL_ID_DEV = "YCZH.TOA3.Dev"

_VT_LPWSTR = 31
_VT_EMPTY = 0

# {9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}
_FMTID_APPUSERMODEL = (
    0x9F4C2855,
    0x9F79,
    0x4B39,
    (0xA8, 0xD0, 0xE1, 0xD4, 0x2D, 0xE1, 0xD5, 0xF3),
)

_STORED: dict[str, str] = {
    "display_name": "运营宝 TOA3",
    "aumid": APP_USER_MODEL_ID,
}


class _GUID(Structure):
    _fields_ = [
        ("Data1", c_ulong),
        ("Data2", c_ushort),
        ("Data3", c_ushort),
        ("Data4", c_byte * 8),
    ]


class _PROPERTYKEY(Structure):
    _fields_ = [("fmtid", _GUID), ("pid", c_ulong)]


class _PROPVARIANT(Structure):
    """x64 精简布局：仅用于 VT_LPWSTR 写入 IPropertyStore。"""

    _fields_ = [
        ("vt", c_ushort),
        ("wReserved1", c_ushort),
        ("wReserved2", c_ushort),
        ("wReserved3", c_ushort),
        ("pwszVal", c_void_p),
        ("_pad", c_byte * (24 - 16)),
    ]


def _guid_appusermodel() -> _GUID:
    g = _GUID()
    g.Data1 = _FMTID_APPUSERMODEL[0]
    g.Data2 = _FMTID_APPUSERMODEL[1]
    g.Data3 = _FMTID_APPUSERMODEL[2]
    for i, b in enumerate(_FMTID_APPUSERMODEL[3]):
        g.Data4[i] = b
    return g


def _pkey(pid: int) -> _PROPERTYKEY:
    key = _PROPERTYKEY()
    key.fmtid = _guid_appusermodel()
    key.pid = pid
    return key


def _taskbar_display_name(explicit: str | None = None) -> str:
    try:
        from services.app_branding import is_development_profile

        if is_development_profile():
            return "运营宝 TOA3 (开发)"
    except Exception:
        pass
    text = str(explicit or _STORED.get("display_name") or "运营宝 TOA3").strip()
    return text or "运营宝 TOA3"


def _resolve_aumid() -> str:
    try:
        from services.app_branding import is_development_profile

        if is_development_profile():
            return APP_USER_MODEL_ID_DEV
    except Exception:
        pass
    return APP_USER_MODEL_ID


def _relaunch_command() -> str:
    try:
        from services.runtime_paths import is_frozen

        if is_frozen():
            return f'"{sys.executable}"'
    except Exception:
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}"'
    try:
        from services.config_service import project_root

        root = str(project_root())
    except Exception:
        root = os.getcwd()
    py = sys.executable
    # 固定工作目录，避免任务栏「重新打开」落在 System32
    return (
        f'"{py}" -c "import os,runpy; os.chdir(r\'{root}\'); '
        f"runpy.run_module('app.main', run_name='__main__')\""
    )


def _relaunch_icon() -> str:
    try:
        from services.app_branding import resolve_app_icon_ico

        ico = resolve_app_icon_ico()
        if ico is not None and ico.is_file():
            return f"{ico},0"
    except Exception:
        pass
    return f"{sys.executable},0"


def apply_windows_app_identity(*, display_name: str | None = None) -> None:
    """须在创建 QApplication 之前调用。"""
    if sys.platform != "win32":
        return
    aumid = _resolve_aumid()
    name = _taskbar_display_name(display_name)
    _STORED["display_name"] = name
    _STORED["aumid"] = aumid
    try:
        windll.shell32.SetCurrentProcessExplicitAppUserModelID(aumid)
    except Exception:
        logger.debug("SetCurrentProcessExplicitAppUserModelID failed", exc_info=True)


def _ole32():
    """x64 下必须声明 restype，否则 CoTaskMemAlloc 指针会被截成 32 位。"""
    ole32 = windll.ole32
    ole32.CoTaskMemAlloc.restype = c_void_p
    ole32.CoTaskMemAlloc.argtypes = [c_size_t]
    ole32.CoTaskMemFree.argtypes = [c_void_p]
    ole32.PropVariantClear.argtypes = [POINTER(_PROPVARIANT)]
    ole32.PropVariantClear.restype = HRESULT
    return ole32


def _propvariant_lpwstr(text: str) -> _PROPVARIANT:
    ole32 = _ole32()
    data = create_unicode_buffer(text)
    nbytes = (len(text) + 1) * sizeof(c_wchar)
    ptr = ole32.CoTaskMemAlloc(nbytes)
    if not ptr:
        raise MemoryError("CoTaskMemAlloc failed")
    memmove(ptr, data, nbytes)
    pv = _PROPVARIANT()
    pv.vt = _VT_LPWSTR
    pv.pwszVal = ptr
    return pv


def _propvariant_clear(pv: _PROPVARIANT) -> None:
    ole32 = _ole32()
    try:
        ole32.PropVariantClear(byref(pv))
    except Exception:
        if pv.vt == _VT_LPWSTR and pv.pwszVal:
            try:
                ole32.CoTaskMemFree(pv.pwszVal)
            except Exception:
                pass
        pv.vt = _VT_EMPTY
        pv.pwszVal = None


def _set_window_propstore(hwnd: int, *, display_name: str, aumid: str, command: str, icon: str) -> None:
    """通过 SHGetPropertyStoreForWindow 写入 Relaunch* + AppUserModel.ID。"""
    if hwnd <= 0:
        return

    from ctypes import WINFUNCTYPE

    shell32 = windll.shell32

    # IID_IPropertyStore = {886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}
    iid = _GUID()
    iid.Data1 = 0x886D8EEB
    iid.Data2 = 0x8CF2
    iid.Data3 = 0x4446
    for i, b in enumerate((0x8D, 0x02, 0xCD, 0xBA, 0x1D, 0xBD, 0xCF, 0x99)):
        iid.Data4[i] = b

    store = c_void_p()
    hr = shell32.SHGetPropertyStoreForWindow(HWND(hwnd), byref(iid), byref(store))
    if hr != 0 or not store.value:
        raise OSError(f"SHGetPropertyStoreForWindow failed hr=0x{hr & 0xFFFFFFFF:08X}")

    # COM 对象首指针即 vtable；IPropertyStore: QI,AddRef,Release,GetCount,GetAt,GetValue,SetValue,Commit
    vtbl = cast(c_void_p.from_address(store.value).value, POINTER(c_void_p))
    SetValue = WINFUNCTYPE(HRESULT, c_void_p, POINTER(_PROPERTYKEY), POINTER(_PROPVARIANT))(vtbl[6])
    Commit = WINFUNCTYPE(HRESULT, c_void_p)(vtbl[7])
    Release = WINFUNCTYPE(c_ulong, c_void_p)(vtbl[2])

    pairs = (
        (2, command),  # RelaunchCommand
        (3, icon),  # RelaunchIconResource
        (4, display_name),  # RelaunchDisplayNameResource
        (5, aumid),  # ID —— 最后写，触发任务栏刷新
    )
    try:
        for pid, value in pairs:
            pv = _propvariant_lpwstr(value)
            try:
                hr2 = SetValue(store, byref(_pkey(pid)), byref(pv))
                if hr2 != 0:
                    raise OSError(f"IPropertyStore.SetValue({pid}) hr=0x{hr2 & 0xFFFFFFFF:08X}")
            finally:
                _propvariant_clear(pv)
        hr3 = Commit(store)
        if hr3 != 0:
            raise OSError(f"IPropertyStore.Commit hr=0x{hr3 & 0xFFFFFFFF:08X}")
    finally:
        Release(store)


def apply_window_taskbar_identity(widget: Any, *, display_name: str | None = None) -> None:
    """在窗口已有 HWND 后调用（show 之后），把跳转列表「Python」改成应用名。"""
    if sys.platform != "win32" or widget is None:
        return
    try:
        wid = int(widget.winId())
    except Exception:
        return
    if wid <= 0:
        return
    name = _taskbar_display_name(display_name)
    aumid = str(_STORED.get("aumid") or _resolve_aumid())
    try:
        _set_window_propstore(
            wid,
            display_name=name,
            aumid=aumid,
            command=_relaunch_command(),
            icon=_relaunch_icon(),
        )
        logger.debug("taskbar identity applied hwnd=%s name=%s", wid, name)
        if not getattr(widget, "_toa_taskbar_id_logged", False):
            logger.info("任务栏身份: %s (AUMID=%s)", name, aumid)
            try:
                widget._toa_taskbar_id_logged = True
            except Exception:
                pass
    except Exception:
        logger.debug("apply_window_taskbar_identity failed", exc_info=True)


def wire_taskbar_activate(shell) -> None:
    """任务栏点击 / 系统「激活应用」时：若主窗藏在托盘则恢复。"""
    if shell is None:
        return
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    # show 前后各刷一次：避免 HWND 未就绪或资源管理器仍缓存「Python」
    def _apply() -> None:
        apply_window_taskbar_identity(shell)

    _apply()
    QTimer.singleShot(0, _apply)
    QTimer.singleShot(300, _apply)

    app = QApplication.instance()
    if app is None:
        return

    def _on_state(state) -> None:
        from PySide6.QtCore import Qt

        if state != Qt.ApplicationState.ApplicationActive:
            return
        try:
            # 仅恢复「藏进托盘」的主窗；已可见时不要抢焦点
            if not shell.isVisible():
                show = getattr(shell, "_show_from_tray", None)
                if callable(show):
                    show()
                else:
                    shell.showNormal()
                    shell.raise_()
                    shell.activateWindow()
        except Exception:
            logger.debug("taskbar activate restore failed", exc_info=True)

    # 避免重复连接
    if getattr(shell, "_toa_taskbar_activate_wired", False):
        return
    shell._toa_taskbar_activate_wired = True
    app.applicationStateChanged.connect(_on_state)
