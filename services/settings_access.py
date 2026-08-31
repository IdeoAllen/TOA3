# -*- coding: utf-8 -*-
"""系统设置可见性：管理员 vs 终端用户。"""
from __future__ import annotations

from typing import Final

# 顶层页签 key
TAB_SYSTEM: Final = "system"
TAB_PREFERENCES: Final = "preferences"
TAB_MODELS: Final = "models"
TAB_EXTENSIONS: Final = "extensions"
TAB_LOCAL_ADMIN: Final = "local_admin"
TAB_SUBSCRIPTION: Final = "subscription"
TAB_OPS_CONSOLE: Final = "ops_console"

# 兼容旧 key
TAB_APP: Final = "app"
TAB_APPEARANCE: Final = "appearance"
TAB_BRAND: Final = "brand"
TAB_LICENSE: Final = "license"
TAB_MENU: Final = "menu"
TAB_HOTKEYS: Final = "hotkeys"
TAB_INTEGRATIONS: Final = "integrations"
TAB_MODELS_AI: Final = "models_ai"
TAB_DIAGNOSTICS: Final = "diagnostics"
TAB_APP_UPDATE: Final = "app_update"
TAB_ABOUT_APP: Final = "about_app"

_TAB_TITLES: dict[str, str] = {
    TAB_SYSTEM: "系统",
    TAB_PREFERENCES: "偏好",
    TAB_MODELS: "模型管理",
    TAB_EXTENSIONS: "扩展",
    TAB_LOCAL_ADMIN: "本机管理",
    TAB_SUBSCRIPTION: "开通与续费",
    TAB_OPS_CONSOLE: "运营台",
    TAB_APP: "系统",
    TAB_APPEARANCE: "外观与主题",
    TAB_BRAND: "品牌定制",
    TAB_LICENSE: "授权管理",
    TAB_MENU: "菜单",
    TAB_HOTKEYS: "快捷键",
    TAB_INTEGRATIONS: "能力接入",
    TAB_MODELS_AI: "模型管理",
    TAB_DIAGNOSTICS: "运行诊断",
    TAB_APP_UPDATE: "应用与更新",
    TAB_ABOUT_APP: "关于产品",
}


def subscription_tab_visible() -> bool:
    """未完整授权时展示开通页。"""
    try:
        from services.license_manager import global_license_manager

        return not global_license_manager.is_licensed()
    except Exception:
        return True


def is_settings_admin() -> bool:
    """当前登录用户是否为管理员（可进运维向设置）。"""
    try:
        from services.license_manager import global_license_manager

        return bool(global_license_manager.is_admin_user())
    except Exception:
        return False


def can_switch_local_identity() -> bool:
    """仅管理员且本机有多于一个已发卡账号时可切换身份。"""
    if not is_settings_admin():
        return False
    try:
        from services.license_manager import global_license_manager

        return len(global_license_manager.list_switchable_users()) > 1
    except Exception:
        return False


def settings_menu_plan() -> list[tuple[str, str]]:
    """左侧菜单 (key, title) 扁平列表（来自 settings_menu 配置）。"""
    from services.settings_menu import settings_menu_flat

    return [(item.key, item.title) for item in settings_menu_flat()]


def settings_tab_plan() -> list[tuple[str, str]]:
    """兼容旧名：与 settings_menu_plan 相同。"""
    return settings_menu_plan()


def resolve_settings_menu_key(key: str) -> str:
    """将旧 key 映射为左侧菜单 key。"""
    top, sub = resolve_settings_tab(key)
    if sub:
        return sub
    if top == TAB_LOCAL_ADMIN:
        return TAB_BRAND
    return top


def settings_header_subtitle() -> str:
    return "左侧选择设置分区；也可从系统侧栏进入；换授权码点顶栏用户。"


def capability_settings_tab_key() -> str:
    return TAB_MODELS


def license_settings_tab_key() -> str:
    if is_settings_admin():
        return TAB_LICENSE
    if subscription_tab_visible():
        return TAB_SUBSCRIPTION
    return TAB_SYSTEM


def resolve_settings_tab(key: str) -> tuple[str, str | None]:
    """将旧 key 或子页 key 映射为 (顶层页签, 本机管理子页 key|None)。"""
    k = str(key or "").strip()
    if k in (TAB_SYSTEM, TAB_APP, TAB_APP_UPDATE, TAB_ABOUT_APP):
        return TAB_SYSTEM, None
    if k in (
        TAB_PREFERENCES,
        TAB_LOCAL_ADMIN,
        TAB_SUBSCRIPTION,
        TAB_MODELS,
        TAB_MODELS_AI,
        TAB_OPS_CONSOLE,
    ):
        if k == TAB_MODELS_AI:
            return TAB_MODELS, None
        return k, None
    # 旧「设置·扩展」页签已迁到系统侧栏模块 user_extensions
    if k == TAB_EXTENSIONS:
        return TAB_SYSTEM, None
    if k in (TAB_BRAND, TAB_LICENSE, TAB_MENU, TAB_INTEGRATIONS, TAB_DIAGNOSTICS):
        return TAB_LOCAL_ADMIN, k
    if k in (TAB_APPEARANCE, TAB_HOTKEYS):
        return TAB_PREFERENCES, k
    return k, None
