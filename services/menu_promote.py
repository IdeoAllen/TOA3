# -*- coding: utf-8 -*-
"""菜单：二级功能 → 一级顶栏子模块（本机 menu.yml，即时保存）。"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from services.config_service import (
    get_all_menu_items,
    get_group_labels,
    get_group_order,
    load_config,
    save_menu_items,
)
from services.menu_registry import is_custom_group_id, normalize_group_order, normalize_menu_group_id

# 系统入口不可提升（与系统设置 · 菜单一致）
PROMOTE_BLOCK_IDS = frozenset(
    {
        "home",
        "system_settings",
        "theme_preview",
        "user_extensions",
        "job_scheduler",
        "notifications",
        "__about__",
    }
)
DEMOTE_BLOCK_GROUPS = frozenset({"home", "system"})


def _factory_group(module_id: str) -> str:
    cfg = load_config()
    menu = cfg.get("menu") or {}
    for item in menu.get("menu_items") or []:
        if isinstance(item, dict) and str(item.get("id") or "") == module_id:
            return normalize_menu_group_id(item.get("group") or "business")
    return "business"


def is_top_level_module(module_id: str, *, item: dict | None = None) -> bool:
    """该功能是否已升为独立顶栏子模块（group == id）。"""
    mid = str(module_id or "").strip()
    if not mid:
        return False
    if item is None:
        from services.config_service import get_menu_item_by_id

        item = get_menu_item_by_id(mid) or {}
    return normalize_menu_group_id(item.get("group")) == mid


def promote_module_to_top_level(module_id: str) -> tuple[bool, str]:
    """将功能模块提升为独立顶栏 Tab，并立即写入本机 menu.yml。"""
    mid = str(module_id or "").strip()
    if not mid:
        return False, "无效模块"
    if mid in PROMOTE_BLOCK_IDS:
        return False, "系统入口不可置为一级菜单"
    items = deepcopy(get_all_menu_items())
    target: dict[str, Any] | None = None
    for it in items:
        if str(it.get("id") or "") == mid:
            target = it
            break
    if target is None:
        return False, "找不到该功能模块"
    name = str(target.get("name") or mid)
    if normalize_menu_group_id(target.get("group")) == mid:
        return False, f"「{name}」已是一级菜单"
    old_gid = normalize_menu_group_id(target.get("group") or "business")
    target["group"] = mid
    labels = dict(get_group_labels())
    labels[mid] = name
    order = list(get_group_order())
    if mid not in order:
        try:
            pos = order.index(old_gid)
            order.insert(pos + 1, mid)
        except ValueError:
            order.append(mid)
    order = normalize_group_order(
        order,
        extra_allowed=[mid, *(str(x.get("group") or "") for x in items)],
    )
    save_menu_items(items, group_labels=labels, group_order=order)
    return True, f"已将「{name}」置为一级菜单"


def demote_module_from_top_level(
    module_id: str,
    *,
    target_group: str | None = None,
) -> tuple[bool, str]:
    """取消独立顶栏 Tab，并回原出厂子模块（或指定 group）。"""
    mid = str(module_id or "").strip()
    if not mid:
        return False, "无效模块"
    items = deepcopy(get_all_menu_items())
    target: dict[str, Any] | None = None
    for it in items:
        if str(it.get("id") or "") == mid:
            target = it
            break
    if target is None:
        return False, "找不到该功能模块"
    name = str(target.get("name") or mid)
    cur_gid = normalize_menu_group_id(target.get("group"))
    if cur_gid != mid and not is_custom_group_id(cur_gid):
        return False, f"「{name}」当前不是一级菜单"
    if cur_gid in DEMOTE_BLOCK_GROUPS:
        return False, "「首页」「系统」不可降级"
    dest = normalize_menu_group_id(target_group or _factory_group(mid))
    if dest == mid:
        dest = "business"
    target["group"] = dest
    labels = dict(get_group_labels())
    order = list(get_group_order())
    # 若该自定义 group 下已无其它模块，从顶栏顺序与标签中移除
    still = any(
        normalize_menu_group_id(it.get("group")) == mid
        for it in items
        if str(it.get("id") or "") != mid
    )
    if not still and is_custom_group_id(mid):
        order = [g for g in order if g != mid]
        labels.pop(mid, None)
    order = normalize_group_order(
        order,
        extra_allowed=[str(it.get("group") or "") for it in items],
    )
    save_menu_items(items, group_labels=labels, group_order=order)
    return True, f"已将「{name}」降回侧栏（{dest}）"
