# -*- coding: utf-8 -*-
"""全局壳能力配置点档案（热键 / 唤起 / 拖入 / 托盘）。

真相源键均在 `config/app.yml` → `hotkeys`（用户可覆盖 `data/user`）。
Win 现行实现；Mac 列为适配口径（未实现勿当已支持）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GlobalFeature:
    """一条可配置的全局壳能力。"""

    id: str
    title: str
    config_keys: tuple[str, ...]
    layer: str  # Ambient | Summon | Overlay | Shell | App
    win_impl: str
    mac_plan: str
    verify: str


# 档案：发版门禁 / 设置页 / Mac 移植对照同一张表
GLOBAL_FEATURES: tuple[GlobalFeature, ...] = (
    GlobalFeature(
        id="double_ctrl_summon",
        title="双击修饰键唤起主窗",
        config_keys=("enable_global_toggle", "toggle_window", "summon_module_id"),
        layer="Summon",
        win_impl="WH_KEYBOARD_LL · services/double_ctrl_summon.py；默认 Double+Ctrl",
        mac_plan="CGEvent tap / NSEvent 双击 ⌘ 或可配双击 ⌃；禁止依赖 RegisterHotKey",
        verify="enable 时 hook 可安装；disable 时 stop",
    ),
    GlobalFeature(
        id="screenshot_hotkeys",
        title="截图全局热键",
        config_keys=("enable_screenshot", "screenshot", "screenshot_region"),
        layer="Overlay",
        win_impl="RegisterHotKey + ApplicationShortcut 兜底 · global_hotkey_bindings",
        mac_plan="Carbon/Cocoa 全局快捷键或 MAS 权限说明；键位默认改 ⌥A / ⌥⇧A",
        verify="enable 时配置可解析；bindings 含两键",
    ),
    GlobalFeature(
        id="module_summon_hotkeys",
        title="模块全局唤起",
        config_keys=("module_shortcuts", "open_notepad", "open_clipboard", "open_ocr", "open_pomodoro", "open_harness_agent"),
        layer="Summon",
        win_impl="RegisterHotKey · module_hotkeys.global_module_bindings",
        mac_plan="同全局快捷键抽象；避免与系统 ⌘Q/⌘H 冲突",
        verify="各有效 seq 可 _parse_hotkey",
    ),
    GlobalFeature(
        id="immersive_fullscreen",
        title="沉浸全屏",
        config_keys=("toggle_fullscreen", "enable_immersive_hotkey"),
        layer="Shell",
        win_impl="ApplicationShortcut F11 · shell._toggle_fullscreen（禁止 RegisterHotKey）",
        mac_plan="默认 ⌃⌘F；仅前台 ApplicationShortcut",
        verify="键可解析；enable 时进窗内映射",
    ),
    GlobalFeature(
        id="app_exit_restart",
        title="退出 / 重启",
        config_keys=("exit_app", "restart_app"),
        layer="App",
        win_impl="ApplicationShortcut · shell._quit_app / _restart_app",
        mac_plan="退出默认 ⌘Q；重启可 ⌘⌃R；走同一 lifecycle API",
        verify="键可解析且带修饰",
    ),
    GlobalFeature(
        id="close_to_tray",
        title="关闭进托盘",
        config_keys=("close_to_background",),
        layer="Shell",
        win_impl="shell._close_to_tray · platform_experience",
        mac_plan="菜单栏额外图标（NSStatusItem）；关闭行为与 Win 托盘对等",
        verify="配置布尔可读",
    ),
    GlobalFeature(
        id="drop_open_desktop",
        title="拖入文件打开桌面浏览",
        config_keys=("enable_drop_open_desktop",),
        layer="Shell",
        win_impl="shell.dropEvent → open_drop_paths → column_preview",
        mac_plan="Qt drop 已跨平台；启动参数 open 文件同路径",
        verify="enable 默认 true；open_drop_paths 可调用",
    ),
    GlobalFeature(
        id="tray_menu",
        title="托盘快捷模块",
        config_keys=("tray_modules",),
        layer="Summon",
        win_impl="tray_service + platform_experience",
        mac_plan="菜单栏下拉复用同一 model",
        verify="列表为非空 id 串",
    ),
    GlobalFeature(
        id="command_palette",
        title="命令面板",
        config_keys=(),  # 暂固定 Ctrl+K
        layer="Palette",
        win_impl="shell ApplicationShortcut Ctrl+K",
        mac_plan="默认 ⌘K；后续纳入 hotkeys.command_palette",
        verify="窗内映射含 Ctrl+K（Win）",
    ),
    GlobalFeature(
        id="cycle_domain_tabs",
        title="顶栏主菜单循环切换",
        config_keys=("next_domain", "prev_domain"),
        layer="Shell",
        win_impl="事件过滤 Ctrl+Tab / Ctrl+Shift+Tab + ApplicationShortcut 兜底 · shell.cycle_domain",
        mac_plan="默认 ⌃⇥ / ⌃⇧⇥；仅前台",
        verify="键可解析；窗内映射含 next/prev_domain",
    ),
)


def feature_by_id(fid: str) -> GlobalFeature | None:
    for f in GLOBAL_FEATURES:
        if f.id == fid:
            return f
    return None


def catalog_rows() -> list[dict[str, Any]]:
    return [
        {
            "id": f.id,
            "title": f.title,
            "keys": list(f.config_keys),
            "layer": f.layer,
            "win": f.win_impl,
            "mac": f.mac_plan,
            "verify": f.verify,
        }
        for f in GLOBAL_FEATURES
    ]
