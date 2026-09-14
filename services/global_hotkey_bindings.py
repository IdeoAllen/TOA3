# -*- coding: utf-8 -*-
"""全局 RegisterHotKey 绑定：shell 启动与设置页保存共用同一套逻辑。"""
from __future__ import annotations

import logging
import time
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

_ATTR_LAST_ERRS = "_hotkey_last_errs"
_ATTR_WARNED = "_hotkey_conflict_warned"
_ATTR_OWNER_OK = "_hotkey_owner_ok"
_ATTR_RETRY_AT = "_hotkey_retry_at"
_ATTR_HOOK_OK = "_hotkey_double_ctrl_ok"


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
    """注册 OS 全局热键；返回失败表。"""
    from services.edition_isolation import peer_hotkey_holder_hint, should_register_global_hotkeys

    ok, reason = should_register_global_hotkeys()
    setattr(shell, _ATTR_OWNER_OK, ok)
    if not ok:
        logger.info("跳过全局热键注册: %s", reason)
        get_hotkey_service().clear()
        apply_double_ctrl_summon(shell)
        setattr(shell, _ATTR_HOOK_OK, False)
        shell._global_fullscreen_hotkey_ok = False
        setattr(shell, _ATTR_LAST_ERRS, {})
        setattr(shell, _ATTR_RETRY_AT, 0.0)
        return {}

    bindings = build_global_hotkey_bindings(shell)
    errs = get_hotkey_service().apply(bindings)
    hook_err = apply_double_ctrl_summon(shell)
    setattr(shell, _ATTR_HOOK_OK, not bool(hook_err))
    if hook_err:
        errs["Double+Ctrl"] = hook_err
    setattr(shell, _ATTR_LAST_ERRS, dict(errs))
    if errs:
        # 部分失败：稍后只重试失败项，避免每 4 秒卸掉已成功的 Alt+A
        setattr(shell, _ATTR_RETRY_AT, time.monotonic() + 8.0)
        hint = peer_hotkey_holder_hint()
        logger.warning("全局热键部分失败: %s%s", errs, f" · {hint}" if hint else "")
        _maybe_warn_shell(shell, errs, hint)
        try:
            from services.edition_isolation import release_toa_running
            from services.runtime_paths import is_frozen

            if (not is_frozen()) and release_toa_running() and len(errs) >= 2:
                _status(
                    shell,
                    "开发热键被正式版占用：请托盘退出「运营宝 TOA3」后再试 Alt+A",
                    level="warning",
                )
                setattr(shell, _ATTR_WARNED, True)
        except Exception:
            pass
    else:
        setattr(shell, _ATTR_RETRY_AT, 0.0)
        if getattr(shell, _ATTR_WARNED, False):
            _status(shell, "全局热键已恢复", level="success")
        setattr(shell, _ATTR_WARNED, False)
        logger.info(
            "全局热键已注册: %s",
            ", ".join(get_hotkey_service().active_specs()) or "(无)",
        )

    shell._global_fullscreen_hotkey_ok = False
    return errs


def reconcile_global_hotkeys_for_shell(shell: Any) -> dict[str, str]:
    """周期调和：开发版优先；失败项增量重试；勿反复整表清空。"""
    from services.edition_isolation import should_register_global_hotkeys

    ok, reason = should_register_global_hotkeys()
    prev_ok = getattr(shell, _ATTR_OWNER_OK, None)
    svc = get_hotkey_service()
    last_errs = getattr(shell, _ATTR_LAST_ERRS, None)
    if not isinstance(last_errs, dict):
        last_errs = {}

    if not ok:
        if svc.active_count() or prev_ok is not False:
            logger.info("调和：释放全局热键（%s）", reason)
            svc.clear()
            apply_double_ctrl_summon(shell)
            setattr(shell, _ATTR_HOOK_OK, False)
            setattr(shell, _ATTR_LAST_ERRS, {})
            setattr(shell, _ATTR_OWNER_OK, False)
            setattr(shell, _ATTR_WARNED, False)
            setattr(shell, _ATTR_RETRY_AT, 0.0)
        return {}

    # 刚从「让出」切回，或完全未注册 → 整表绑定一次
    if prev_ok is False or svc.active_count() == 0:
        return apply_global_hotkeys_for_shell(shell)

    now = time.monotonic()
    retry_at = float(getattr(shell, _ATTR_RETRY_AT, 0.0) or 0.0)
    reg_errs = {k: v for k, v in last_errs.items() if k != "Double+Ctrl"}
    hook_needed = bool(last_errs.get("Double+Ctrl")) or not bool(
        getattr(shell, _ATTR_HOOK_OK, True)
    )

    if reg_errs and now >= retry_at:
        bindings = build_global_hotkey_bindings(shell)
        new_errs = svc.register_many(bindings, only_specs=set(reg_errs))
        merged = {k: v for k, v in last_errs.items() if k == "Double+Ctrl"}
        merged.update(new_errs)
        # 仍失败的保留；已成功的从 errs 去掉
        for spec in list(reg_errs):
            if spec not in new_errs:
                merged.pop(spec, None)
        setattr(shell, _ATTR_LAST_ERRS, merged)
        if new_errs:
            setattr(shell, _ATTR_RETRY_AT, now + 15.0)
            logger.info("热键增量重试仍失败: %s", new_errs)
        else:
            setattr(shell, _ATTR_RETRY_AT, 0.0)
            if not merged and getattr(shell, _ATTR_WARNED, False):
                _status(shell, "全局热键已恢复", level="success")
                setattr(shell, _ATTR_WARNED, False)
            logger.info("热键增量重试成功")
        last_errs = merged

    if hook_needed and now >= retry_at:
        new_hook = apply_double_ctrl_summon(shell)
        if new_hook:
            last_errs = dict(last_errs)
            last_errs["Double+Ctrl"] = new_hook
            setattr(shell, _ATTR_HOOK_OK, False)
            setattr(shell, _ATTR_LAST_ERRS, last_errs)
            setattr(shell, _ATTR_RETRY_AT, now + 15.0)
        else:
            last_errs = {k: v for k, v in last_errs.items() if k != "Double+Ctrl"}
            setattr(shell, _ATTR_LAST_ERRS, last_errs)
            setattr(shell, _ATTR_HOOK_OK, True)
            if not last_errs:
                setattr(shell, _ATTR_RETRY_AT, 0.0)
                if getattr(shell, _ATTR_WARNED, False):
                    _status(shell, "全局热键已恢复", level="success")
                    setattr(shell, _ATTR_WARNED, False)
            logger.info("double Ctrl summon hook recovered")

    return getattr(shell, _ATTR_LAST_ERRS, {}) or {}


def _maybe_warn_shell(shell: Any, errs: dict[str, str], hint: str) -> None:
    if getattr(shell, _ATTR_WARNED, False):
        return
    keys = ", ".join(sorted(errs.keys())[:6])
    more = "…" if len(errs) > 6 else ""
    msg = f"全局热键未生效：{keys}{more}"
    if hint:
        msg = f"{msg}。{hint}"
    else:
        msg = f"{msg}（可能被其它软件占用；空闲后将自动重试）"
    _status(shell, msg, level="warning")
    setattr(shell, _ATTR_WARNED, True)


def _status(shell: Any, text: str, *, level: str) -> None:
    try:
        show = getattr(shell, "show_status", None)
        if not callable(show):
            return
        from core.status_service import StatusLevel

        lvl = {
            "warning": StatusLevel.WARNING,
            "success": StatusLevel.SUCCESS,
            "error": StatusLevel.ERROR,
            "info": StatusLevel.INFO,
        }.get(level, StatusLevel.INFO)
        show(text, level=lvl)
    except Exception:
        logger.debug("hotkey status notify failed", exc_info=True)
