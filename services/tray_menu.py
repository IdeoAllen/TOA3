# -*- coding: utf-8 -*-
"""托盘菜单：与 menu_registry / 热键同源，禁止硬编码第二套功能列表。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from services.access_control import can_open
from services.config_service import get_hotkeys_config
from services.menu_registry import get_menu_item_by_id, is_migrated
from services.module_hotkeys import get_module_shortcut

DEFAULT_TRAY_MODULES: tuple[str, ...] = (
    "quick_notepad",
    "clipboard_history",
    "screenshot_tool",
    "quadrant_tasks",
    "ocr_tool",
    "harness_agent",
)

# 托盘走 Summon/热键路径，不进截图页
_TRAY_EXCLUDE_PAGE_ONLY: frozenset[str] = frozenset({"screenshot_tool"})


@dataclass(frozen=True)
class TrayMenuEntry:
    module_id: str
    title: str
    shortcut: str
    summon: Callable[[], None] | None


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


def build_tray_entries(
    *,
    summon_module: Callable[[str], None],
    screenshot_region: Callable[[], None] | None = None,
    screenshot_full: Callable[[], None] | None = None,
    open_clipboard: Callable[[], None] | None = None,
) -> list[TrayMenuEntry]:
    """可 Summon 的模块 + 截图/剪贴板快捷动作。"""
    entries: list[TrayMenuEntry] = []
    seen: set[str] = set()

    for mid in tray_module_ids():
        if mid in seen or mid in _TRAY_EXCLUDE_PAGE_ONLY:
            continue
        if not is_migrated(mid):
            continue
        ok, _ = can_open(mid)
        if not ok:
            continue
        item = get_menu_item_by_id(mid) or {}
        title = str(item.get("name") or mid)
        seq = get_module_shortcut(mid)
        entries.append(
            TrayMenuEntry(
                module_id=mid,
                title=title,
                shortcut=seq,
                summon=lambda m=mid: summon_module(m),
            )
        )
        seen.add(mid)

    hk = get_hotkeys_config()
    if hk.get("enable_screenshot", True):
        if screenshot_region and hk.get("screenshot"):
            seq = str(hk.get("screenshot") or "")
            entries.append(
                TrayMenuEntry("screenshot_region", "区域截图", seq, screenshot_region)
            )
        if screenshot_full and hk.get("screenshot_region"):
            seq = str(hk.get("screenshot_region") or "")
            entries.append(
                TrayMenuEntry("screenshot_full", "全屏截图", seq, screenshot_full)
            )
    if open_clipboard and "clipboard_history" not in seen:
        ok, _ = can_open("clipboard_history")
        if ok and "clipboard_history" not in tray_module_ids():
            seq = get_module_shortcut("clipboard_history")
            entries.append(
                TrayMenuEntry("clipboard_history", "剪贴板历史", seq, open_clipboard)
            )
    return entries
