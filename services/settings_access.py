# -*- coding: utf-8 -*-
"""系统设置可见性：管理员 vs 终端用户。"""
from __future__ import annotations

from typing import Final

# 页签 key（导航用，与 UI 标题解耦）
TAB_APPEARANCE: Final = "appearance"
TAB_BRAND: Final = "brand"
TAB_LICENSE: Final = "license"
TAB_SUBSCRIPTION: Final = "subscription"
TAB_MENU: Final = "menu"
TAB_HOTKEYS: Final = "hotkeys"
TAB_INTEGRATIONS: Final = "integrations"
TAB_MODELS_AI: Final = "models_ai"
TAB_DIAGNOSTICS: Final = "diagnostics"
TAB_ABOUT_APP: Final = "about_app"

_USER_TAB_KEYS: tuple[str, ...] = (
    TAB_APPEARANCE,
    TAB_HOTKEYS,
    TAB_MODELS_AI,
    TAB_ABOUT_APP,
)

_ADMIN_EXTRA_TAB_KEYS: tuple[str, ...] = (
    TAB_BRAND,
    TAB_LICENSE,
    TAB_MENU,
    TAB_INTEGRATIONS,
    TAB_DIAGNOSTICS,
)

_TAB_TITLES: dict[str, str] = {
    TAB_APPEARANCE: "外观与主题",
    TAB_BRAND: "品牌定制",
    TAB_LICENSE: "授权管理",
    TAB_SUBSCRIPTION: "订阅购买",
    TAB_MENU: "菜单",
    TAB_HOTKEYS: "快捷键",
    TAB_INTEGRATIONS: "能力接入",
    TAB_MODELS_AI: "模型与 AI",
    TAB_DIAGNOSTICS: "运行诊断",
    TAB_ABOUT_APP: "关于与应用",
}


def subscription_tab_visible() -> bool:
    """未完整授权时展示订阅/激活页（已联网授权后隐藏）。"""
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


def settings_tab_plan() -> list[tuple[str, str]]:
    """按角色返回 (key, title) 列表。"""
    admin = is_settings_admin()
    order: list[str] = [TAB_APPEARANCE]
    if admin:
        order.append(TAB_BRAND)
        order.append(TAB_LICENSE)
    if subscription_tab_visible():
        order.append(TAB_SUBSCRIPTION)
    if admin:
        order.append(TAB_MENU)
    order.append(TAB_HOTKEYS)
    if admin:
        order.append(TAB_INTEGRATIONS)
    else:
        order.append(TAB_MODELS_AI)
    if admin:
        order.append(TAB_DIAGNOSTICS)
    order.append(TAB_ABOUT_APP)
    return [(k, _TAB_TITLES[k]) for k in order]


def settings_header_subtitle() -> str:
    if is_settings_admin():
        return (
            "管理员：品牌 · 授权 · 菜单 · 能力接入 · 诊断。"
            "终端用户见主题、快捷键与模型 Key。"
            "任务与通知见系统侧栏。"
        )
    return (
        "主题、快捷键、AI 模型 Key。"
        "关于、续费提示与退出见「关于与应用」。"
        "授权名单与菜单编排仅管理员可见。"
    )


def capability_settings_tab_key() -> str:
    """大模型/模型库跳转应打开的页签 key。"""
    return TAB_INTEGRATIONS if is_settings_admin() else TAB_MODELS_AI


def license_settings_tab_key() -> str:
    if is_settings_admin():
        return TAB_LICENSE
    if subscription_tab_visible():
        return TAB_SUBSCRIPTION
    return TAB_ABOUT_APP
