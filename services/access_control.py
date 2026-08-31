# -*- coding: utf-8 -*-
"""访问控制：打开模块前的唯一门禁。"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

from services.runtime_mode import SHELL_MODULE_IDS

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


def _menu_requires_license(item: dict | None) -> bool:
    if isinstance(item, dict) and "requires_license" in item:
        return bool(item.get("requires_license"))
    return True


def _is_basic_module(item: dict | None) -> bool:
    """app.yml requires_license:false → 全版本永久免费（与 SKU/到期无关）。"""
    return not _menu_requires_license(item)


def requires_purchase_redirect() -> bool:
    """体验/试用/付费方案已到期，需统一引导至购买页。"""
    try:
        from services.license_manager import global_license_manager as lm

        if not lm.license_info:
            lm.load_license()
        return bool(
            lm.is_expired_standalone()
            or lm.is_expired_trial()
            or lm.is_expired_paid()
        )
    except Exception:
        return False


def nav_clickable(
    module_id: Optional[str] = None,
    *,
    module_name: Optional[str] = None,
) -> Tuple[bool, str]:
    """侧栏/首页是否可点：到期后付费模块仍可点，由 navigate 统一拦截至购买页。"""
    ok, reason = can_open(module_id, module_name=module_name)
    if ok:
        return True, ""
    if not requires_purchase_redirect():
        return False, reason
    mid = (module_id or "").strip()
    item = None
    if mid:
        from services.config_service import get_menu_item_by_id

        item = get_menu_item_by_id(mid)
    if item is None and module_name:
        from services.menu_registry import all_menu_items

        for it in all_menu_items():
            if str(it.get("name") or "").strip() == str(module_name or "").strip():
                item = it
                break
    if _is_basic_module(item):
        return ok, reason
    return True, reason


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

    # 基础板块：开发/体验/试用/付费/到期 — 一律永久可用
    if _is_basic_module(item):
        return True, ""

    try:
        from services.license_manager import global_license_manager
        from services.user_plan_presentation import user_access_block_message, user_plan_expired

        lm = global_license_manager
        if not lm.license_info:
            lm.load_license()
    except Exception:
        lm = None  # type: ignore

    if lm is not None:
        if user_plan_expired() or _is_standalone_session():
            return False, user_access_block_message()

    try:
        licensed = bool(lm.is_licensed()) if lm is not None else False
    except Exception:
        licensed = False
        lm = None  # type: ignore

    if lm is not None and (lm.is_expired_trial() or lm.is_expired_paid()):
        return False, user_access_block_message()

    if not licensed:
        if lm is not None and lm.is_expired_paid():
            return False, user_access_block_message()
        try:
            reason = lm.get_license_status_message() if lm is not None else "当前未授权"
        except Exception:
            reason = "当前未授权"
        if lm is not None and lm.had_network_activation() and lm.is_activation_expired():
            return False, user_access_block_message()
        if "到期" in str(reason):
            return False, user_access_block_message()
        return False, user_access_block_message()

    feature_key = mid
    if isinstance(item, dict) and item.get("requires_feature"):
        feature_key = str(item.get("requires_feature") or mid)
    elif isinstance(item, dict) and item.get("feature_id"):
        feature_key = str(item.get("feature_id") or mid)

    if licensed and feature_key:
        try:
            if lm is not None and not lm.has_feature_access(feature_key):
                from services.plan_tiers import upgrade_hint

                hint = upgrade_hint(module_id=feature_key)
                if hint:
                    return False, hint
                return False, f"未包含功能「{name or feature_key}」· 请升级产品方案"
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
