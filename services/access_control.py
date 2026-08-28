# -*- coding: utf-8 -*-
"""访问控制：打开模块前的唯一门禁。"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

from services.runtime_mode import SHELL_MODULE_IDS, local_free_module_ids

_CAN_OPEN_CACHE: Dict[str, Tuple[bool, str]] = {}


def invalidate_can_open_cache() -> None:
    _CAN_OPEN_CACHE.clear()


def _is_standalone_session() -> bool:
    """单机 local_free：读本地 license 标记，不走联网校验。"""
    try:
        from services.license_manager import global_license_manager
        from services.runtime_mode import is_standalone_record

        lm = global_license_manager
        if not lm.license_info:
            lm.load_license()
        if bool(lm.license_info.get("is_licensed")):
            return False
        return is_standalone_record(lm.license_info)
    except Exception:
        return False


def is_admin_session() -> bool:
    try:
        from services.license_manager import global_license_manager

        return bool(global_license_manager.is_admin_user())
    except Exception:
        return False


def has_full_menu_session() -> bool:
    try:
        from services.license_manager import global_license_manager

        return bool(global_license_manager.has_full_menu_access())
    except Exception:
        return False


def can_open(
    module_id: Optional[str] = None,
    *,
    module_name: Optional[str] = None,
) -> Tuple[bool, str]:
    """返回 (是否允许, 拒绝原因)。"""
    mid = (module_id or "").strip()
    cache_key = mid or (module_name or "").strip()
    if cache_key:
        cached = _CAN_OPEN_CACHE.get(cache_key)
        if cached is not None:
            return cached

    result = _can_open_uncached(module_id, module_name=module_name)
    if cache_key:
        _CAN_OPEN_CACHE[cache_key] = result
    return result


def _can_open_uncached(
    module_id: Optional[str] = None,
    *,
    module_name: Optional[str] = None,
) -> Tuple[bool, str]:
    mid = (module_id or "").strip()
    from services.menu_registry import all_menu_items
    from services.config_service import get_menu_item_by_id

    name = (module_name or "").strip()

    if mid in SHELL_MODULE_IDS or name in {
        "首页",
        "系统设置",
        "任务",
        "通知",
        "关于",
    }:
        return True, ""

    if is_admin_session() or has_full_menu_session():
        return True, ""

    item = None
    if mid:
        item = get_menu_item_by_id(mid)
    if item is None and name:
        for it in all_menu_items():
            if str(it.get("name") or "").strip() == name:
                item = it
                break
    if item:
        mid = mid or str(item.get("id") or "")
        name = name or str(item.get("name") or "")

    if _is_standalone_session():
        if mid in local_free_module_ids():
            return True, ""
        return (
            False,
            f"「{name or mid}」属于完整版功能。请使用授权码登录，或在系统设置中激活。",
        )

    try:
        from services.license_manager import global_license_manager

        licensed = bool(global_license_manager.is_licensed())
    except Exception:
        licensed = False
        global_license_manager = None  # type: ignore

    requires_license = True
    if isinstance(item, dict) and "requires_license" in item:
        requires_license = bool(item.get("requires_license"))

    if requires_license and not licensed:
        try:
            reason = global_license_manager.get_license_status_message()
        except Exception:
            reason = "当前未授权"
        if "到期" in str(reason):
            return False, f"{reason}"
        return False, f"{reason}。请使用 TOA 运营台签发的授权码登录。"

    if not requires_license and not licensed:
        return True, ""

    feature_key = mid
    if isinstance(item, dict) and item.get("requires_feature"):
        feature_key = str(item.get("requires_feature") or mid)
    elif isinstance(item, dict) and item.get("feature_id"):
        feature_key = str(item.get("feature_id") or mid)

    if licensed and feature_key:
        try:
            if global_license_manager is not None and not global_license_manager.has_feature_access(
                feature_key
            ):
                return False, f"当前授权未包含功能「{name or feature_key}」，请联系管理员开通。"
        except Exception:
            pass

    return True, ""


def assert_can_open(module_id: Optional[str] = None, *, module_name: Optional[str] = None) -> None:
    ok, reason = can_open(module_id, module_name=module_name)
    if not ok:
        raise PermissionError(reason or "无权限")


def filter_menu_items(items: list[dict]) -> list[dict]:
    """按发行版白名单裁剪；授权在 navigate / 侧栏禁用态处理，避免整组空白。"""
    try:
        from services.edition_profile import filter_menu_by_edition

        items = filter_menu_by_edition(items)
    except Exception:
        pass
    return list(items)
