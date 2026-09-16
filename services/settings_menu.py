# -*- coding: utf-8 -*-
"""系统设置左侧菜单：与 config/app.yml settings_menu 同源。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.settings_access import (
    TAB_BRAND,
    TAB_DIAGNOSTICS,
    TAB_INTEGRATIONS,
    TAB_LICENSE,
    TAB_MENU,
    TAB_MODELS,
    TAB_OPS_CONSOLE,
    TAB_PREFERENCES,
    TAB_SUBSCRIPTION,
    TAB_SYSTEM,
    is_settings_admin,
    subscription_tab_visible,
)

_SETTINGS_NAV_ICON = 18

# 默认菜单（app.yml 缺失或未配置时 fallback）
_DEFAULT_GROUPS: list[dict[str, Any]] = [
    {
        "id": "general",
        "label": "通用",
        "items": [
            {
                "key": TAB_SYSTEM,
                "title": "关于",
                "icon": "system_settings",
                "subtitle": "检查更新、关于与运行",
            },
            {
                "key": TAB_PREFERENCES,
                "title": "偏好",
                "icon": "theme",
                "subtitle": "主题配色与全局快捷键",
            },
            {
                "key": TAB_MODELS,
                "title": "模型管理",
                "icon": "llm_assistant",
                "subtitle": "算力来源 · 绑定 · 设默认 · 解绑",
            },
        ],
    },
    {
        "id": "ops",
        "label": "运营台与商业",
        "items": [
            {
                "key": TAB_OPS_CONSOLE,
                "title": "运营台",
                "icon": "package",
                "subtitle": "打开云服务运营台 · 方案/订单/发版",
            },
            {
                "key": TAB_SUBSCRIPTION,
                "title": "开通与续费",
                "icon": "package",
                "subtitle": "一键开通与粘贴授权码",
                "unlicensed_only": True,
            },
            {
                "key": TAB_LICENSE,
                "title": "授权",
                "icon": "user",
                "subtitle": "本机用户、发卡与云服务连接",
                "admin_only": True,
            },
            {
                "key": TAB_MENU,
                "title": "菜单",
                "icon": "list",
                "subtitle": "侧栏可见性 · 同步目录到运营台",
                "admin_only": True,
            },
        ],
    },
    {
        "id": "admin",
        "label": "本机维护",
        "admin_only": True,
        "items": [
            {
                "key": TAB_BRAND,
                "title": "品牌",
                "icon": "main_window",
                "subtitle": "Logo、名称与关于页文案",
            },
            {
                "key": TAB_INTEGRATIONS,
                "title": "能力接入",
                "icon": "harness_agent",
                "subtitle": "截图识字与本机能力状态",
            },
            {
                "key": TAB_DIAGNOSTICS,
                "title": "诊断",
                "icon": "file_text",
                "subtitle": "运行环境与本机日志",
            },
        ],
    },
]


@dataclass(frozen=True)
class SettingsMenuItem:
    key: str
    title: str
    icon: str
    subtitle: str = ""


@dataclass(frozen=True)
class SettingsMenuGroup:
    id: str
    label: str
    items: tuple[SettingsMenuItem, ...]


def _raw_groups() -> list[dict[str, Any]]:
    try:
        from services.config_service import load_config

        cfg = load_config()
        block = cfg.get("settings_menu") or {}
        groups = block.get("groups")
        if isinstance(groups, list) and groups:
            return groups
    except Exception:
        pass
    return _DEFAULT_GROUPS


def _item_visible(raw: dict[str, Any]) -> bool:
    if raw.get("admin_only") and not is_settings_admin():
        return False
    if raw.get("unlicensed_only") and not subscription_tab_visible():
        return False
    if raw.get("licensed_only") and subscription_tab_visible():
        return False
    return True


def settings_menu_groups() -> list[SettingsMenuGroup]:
    """按角色过滤后的分组菜单（真相源：app.yml settings_menu）。"""
    out: list[SettingsMenuGroup] = []
    for grp in _raw_groups():
        if not isinstance(grp, dict):
            continue
        if grp.get("admin_only") and not is_settings_admin():
            continue
        label = str(grp.get("label") or "").strip()
        gid = str(grp.get("id") or label or "group").strip()
        items_raw = grp.get("items") or []
        items: list[SettingsMenuItem] = []
        for raw in items_raw:
            if not isinstance(raw, dict) or not _item_visible(raw):
                continue
            key = str(raw.get("key") or "").strip()
            if not key:
                continue
            items.append(
                SettingsMenuItem(
                    key=key,
                    title=str(raw.get("title") or key),
                    icon=str(raw.get("icon") or key),
                    subtitle=str(raw.get("subtitle") or ""),
                )
            )
        if items:
            out.append(SettingsMenuGroup(id=gid, label=label, items=tuple(items)))
    return out


def settings_menu_flat() -> list[SettingsMenuItem]:
    flat: list[SettingsMenuItem] = []
    for grp in settings_menu_groups():
        flat.extend(grp.items)
    return flat


def settings_menu_item(key: str) -> SettingsMenuItem | None:
    k = str(key or "").strip()
    for item in settings_menu_flat():
        if item.key == k:
            return item
    return None


def settings_menu_title(key: str) -> str:
    item = settings_menu_item(key)
    return item.title if item else key


def settings_nav_icon_size() -> int:
    return _SETTINGS_NAV_ICON
