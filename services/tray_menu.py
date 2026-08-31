# -*- coding: utf-8 -*-
"""托盘菜单：与 menu_registry / 热键同源（Figma T3 · 分组 Summon / 授权与更新 / 系统）。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from services.access_control import can_open
from services.config_service import get_hotkeys_config
from services.menu_registry import get_menu_item_by_id, is_migrated
from services.module_hotkeys import get_module_shortcut

DEFAULT_TRAY_MODULES: tuple[str, ...] = (
    "screenshot_tool",
    "clipboard_history",
    "quick_notepad",
    "quadrant_tasks",
    "ocr_tool",
    "harness_agent",
)

# 托盘走 Summon/热键路径，不进截图工具页
_SUMMON_AS_OVERLAY: frozenset[str] = frozenset({"screenshot_tool"})


@dataclass(frozen=True)
class TrayMenuEntry:
    module_id: str
    title: str
    shortcut: str
    summon: Callable[[], None] | None


@dataclass(frozen=True)
class TrayMenuModel:
    """Figma T3 目标态结构。"""

    summon: tuple[TrayMenuEntry, ...]
    license_line: str
    show_expiry_action: bool
    expiry_label: str = "授权即将过期"


def tray_module_ids() -> list[str]:
    hk = get_hotkeys_config()
    raw = hk.get("tray_modules")
    if isinstance(raw, list) and raw:
        out: list[str] = []
        for mid in raw:
            s = str(mid or "").strip()
            if s and s not in out:
                out.append(s)
        return out
    return list(DEFAULT_TRAY_MODULES)


def _menu_title(module_id: str) -> str:
    item = get_menu_item_by_id(module_id) or {}
    return str(item.get("name") or module_id)


def build_tray_menu_model(
    *,
    summon_module: Callable[[str], None],
    screenshot_region: Callable[[], None] | None = None,
    screenshot_full: Callable[[], None] | None = None,
    open_clipboard: Callable[[], None] | None = None,
) -> TrayMenuModel:
    """Summon 项来自 menu_registry + 热键；授权摘要见 user_status_plan_label。"""
    summon: list[TrayMenuEntry] = []
    seen: set[str] = set()
    hk = get_hotkeys_config()

    for mid in tray_module_ids():
        if mid in seen:
            continue
        if not is_migrated(mid):
            continue
        ok, _ = can_open(mid)
        if not ok:
            continue

        title = _menu_title(mid)
        seq = get_module_shortcut(mid)

        if mid in _SUMMON_AS_OVERLAY:
            fn = screenshot_region
            if fn is None:
                continue
            if not hk.get("enable_screenshot", True):
                continue
            seq = str(hk.get("screenshot") or seq or "")
        elif mid == "clipboard_history" and open_clipboard is not None:
            fn = open_clipboard
        else:
            fn = lambda _checked=False, m=mid: summon_module(m)

        summon.append(
            TrayMenuEntry(
                module_id=mid,
                title=title,
                shortcut=seq,
                summon=fn,
            )
        )
        seen.add(mid)

    if hk.get("enable_screenshot", True) and screenshot_full and hk.get("screenshot_region"):
        seq = str(hk.get("screenshot_region") or "")
        summon.append(
            TrayMenuEntry(
                module_id="screenshot_full",
                title="全屏截图",
                shortcut=seq,
                summon=screenshot_full,
            )
        )

    license_line = "—"
    show_expiry = False
    try:
        from services.user_plan_presentation import user_status_plan_label

        license_line = user_status_plan_label()
    except Exception:
        pass

    try:
        from services.license_manager import global_license_manager as lm

        if lm.is_licensed() and not lm.is_standalone_mode():
            days = lm.get_remaining_days()
            if days != float("inf") and 0 <= int(days) <= 7:
                show_expiry = True
    except Exception:
        pass

    return TrayMenuModel(
        summon=tuple(summon),
        license_line=license_line,
        show_expiry_action=show_expiry,
    )


def build_tray_entries(
    *,
    summon_module: Callable[[str], None],
    screenshot_region: Callable[[], None] | None = None,
    screenshot_full: Callable[[], None] | None = None,
    open_clipboard: Callable[[], None] | None = None,
) -> list[TrayMenuEntry]:
    """兼容旧调用：返回 Summon 扁平列表。"""
    model = build_tray_menu_model(
        summon_module=summon_module,
        screenshot_region=screenshot_region,
        screenshot_full=screenshot_full,
        open_clipboard=open_clipboard,
    )
    return list(model.summon)
