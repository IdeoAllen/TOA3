# -*- coding: utf-8 -*-
"""全局 RegisterHotKey 绑定：shell 启动与设置页保存共用同一套逻辑。"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from services.config_service import get_hotkeys_config
from services.double_ctrl_summon import apply_double_ctrl_summon, is_double_ctrl_spec
from services.hotkey_service import get_hotkey_service
from services.module_hotkeys import global_module_bindings, normalize_module_id
from services.screenshot_service import run_screenshot_hotkey

if TYPE_CHECKING:
    from app.shell import MainShell

logger = logging.getLogger(__name__)


def build_global_hotkey_bindings(shell: "MainShell") -> dict[str, Callable[[], None]]:
    """hotkey_spec -> callback（不含 edition 隔离判断）。"""
    hk = get_hotkeys_config()
    bindings: dict[str, Callable[[], None]] = {}
    if hk.get("enable_screenshot", True):
        if hk.get("screenshot"):
            bindings[str(hk["screenshot"])] = lambda: run_screenshot_hotkey(shell, full=False)
        if hk.get("screenshot_region"):
            bindings[str(hk["screenshot_region"])] = lambda: run_screenshot_hotkey(
                shell, full=True
            )
    # F11 / 沉浸键禁止 RegisterHotKey：正式版会系统级抢走开发版按键。
    # 沉浸只在本窗前台有意义 → ApplicationShortcut + _ShellNavKeyFilter。
    tw_key = str(hk.get("toggle_window") or "").strip()
    if (
        tw_key
        and tw_key.lower() != "none"
        and not is_double_ctrl_spec(tw_key)
    ):
        summon_id = normalize_module_id(hk.get("summon_module_id"))
        if summon_id:
            bindings[tw_key] = lambda: shell._summon_module(summon_id)
        else:
            bindings[tw_key] = shell._show_from_tray
    for seq, mid in global_module_bindings().items():
        if seq in bindings:
            continue
        if mid == "ocr_tool":
            bindings[seq] = shell._run_ocr_hotkey
        elif mid == "clipboard_history":
            bindings[seq] = shell._open_clipboard_quick
        else:
            bindings[seq] = lambda _checked=False, m=mid: shell._summon_module(m)
    return bindings


def apply_global_hotkeys_for_shell(shell: Any) -> dict[str, str]:
    """注册 OS 全局热键；返回失败表。开发版与正式版并存时跳过注册。"""
    from services.edition_isolation import should_register_global_hotkeys

    ok, reason = should_register_global_hotkeys()
    if not ok:
        logger.info("跳过全局热键注册: %s", reason)
        get_hotkey_service().clear()
        apply_double_ctrl_summon(shell)
        shell._global_fullscreen_hotkey_ok = False
        return {}

    bindings = build_global_hotkey_bindings(shell)
    errs = get_hotkey_service().apply(bindings)
    hook_err = apply_double_ctrl_summon(shell)
    if hook_err:
        errs["Double+Ctrl"] = hook_err
    if errs:
        logger.info("全局热键部分失败: %s", errs)

    # 沉浸全屏仅应用内处理，不占用 OS 全局 F11
    shell._global_fullscreen_hotkey_ok = False
    return errs
