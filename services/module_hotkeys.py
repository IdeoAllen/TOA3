# -*- coding: utf-8 -*-
"""模块级快捷键：读取 hotkeys.module_shortcuts，兼容旧 open_* 键。"""
from __future__ import annotations

from services.config_service import get_all_menu_items, get_hotkeys_config
from services.menu_registry import group_label, grouped_menu_items, is_migrated

# module_id -> hotkeys 顶层旧键（向后兼容）
_LEGACY_TOP_KEYS: dict[str, str] = {
    "quick_notepad": "open_notepad",
    "pomodoro": "open_pomodoro",
    "ocr_tool": "open_ocr",
    "clipboard_history": "open_clipboard",
    "harness_agent": "open_harness_agent",
    "home": "open_home",
}

# module_id -> 默认快捷键（未配置时首页卡片展示用）
_DEFAULT_SHORTCUTS: dict[str, str] = {
    "quick_notepad": "Alt+N",
    "pomodoro": "Alt+P",
    "screenshot_tool": "Alt+A",
    "ocr_tool": "Alt+O",
    "clipboard_history": "Alt+Shift+C",
    "harness_agent": "Alt+Shift+H",
    "home": "Ctrl+H",
}

# 设置页默认展示（常用唤起）；其余用 Ctrl+K / 侧栏，按需「添加模块」
_HOTKEY_EDITOR_CURATED: tuple[str, ...] = (
    "quick_notepad",
    "pomodoro",
    "clipboard_history",
    "harness_agent",
    "quadrant_tasks",
    "deduction_note_formatter",
    "directory_generator",
    "watermark_remover",
    "screenshot_tool",
    "ocr_tool",
)


def _normalize_seq(seq: str) -> str:
    s = str(seq or "").strip()
    if not s or s.lower() == "none":
        return ""
    return s


def get_module_shortcut(module_id: str) -> str:
    """模块有效快捷键（module_shortcuts 优先，其次 legacy 顶层键，最后默认）。"""
    mid = str(module_id or "").strip()
    if not mid:
        return ""
    hk = get_hotkeys_config()
    per = hk.get("module_shortcuts") or {}
    if isinstance(per, dict):
        val = _normalize_seq(str(per.get(mid) or ""))
        if val:
            return val
    legacy_key = _LEGACY_TOP_KEYS.get(mid)
    if legacy_key:
        val = _normalize_seq(str(hk.get(legacy_key) or ""))
        if val:
            return val
    return _DEFAULT_SHORTCUTS.get(mid, "")


def get_configured_module_shortcuts() -> dict[str, str]:
    """用户显式配置的 module_shortcuts（不含 fallback）。"""
    hk = get_hotkeys_config()
    raw = hk.get("module_shortcuts") or {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for mid, seq in raw.items():
        val = _normalize_seq(str(seq or ""))
        if val:
            out[str(mid)] = val
    return out


def list_shortcut_modules_grouped() -> list[tuple[str, str, list[tuple[str, str, str]]]]:
    """按顶栏子模块分组：(group_id, 分组名, [(module_id, 展示名, 有效快捷键), …])。"""
    out: list[tuple[str, str, list[tuple[str, str, str]]]] = []
    for gid, glab, items in grouped_menu_items(licensed_only=False, migrated_only=True):
        rows: list[tuple[str, str, str]] = []
        for item in sorted(items, key=lambda x: (int(x.get("order") or 0), str(x.get("name") or ""))):
            if not item.get("show", True):
                continue
            mid = str(item.get("id") or "").strip()
            if not mid or mid in ("__about__",):
                continue
            name = str(item.get("name") or mid)
            rows.append((mid, name, get_module_shortcut(mid)))
        if rows:
            out.append((gid, glab, rows))
    # 兜底：菜单未登记但已迁移的模块
    orphan: list[tuple[str, str, str]] = []
    listed = {mid for _g, _l, rows in out for mid, _n, _s in rows}
    for item in get_all_menu_items():
        if not item.get("show", True):
            continue
        mid = str(item.get("id") or "").strip()
        if not mid or mid in listed or not is_migrated(mid):
            continue
        orphan.append((mid, str(item.get("name") or mid), get_module_shortcut(mid)))
    if orphan:
        orphan.sort(key=lambda x: x[1])
        out.append(("other", group_label("other"), orphan))
    return out


def list_shortcut_modules() -> list[tuple[str, str, str]]:
    """(module_id, 展示名, 当前有效快捷键)；顺序与菜单一致。"""
    flat: list[tuple[str, str, str]] = []
    for _gid, _glab, rows in list_shortcut_modules_grouped():
        flat.extend(rows)
    return flat


def _menu_name_map() -> dict[str, str]:
    out: dict[str, str] = {}
    for item in get_all_menu_items():
        if not item.get("show", True):
            continue
        mid = str(item.get("id") or "").strip()
        if mid:
            out[mid] = str(item.get("name") or mid)
    return out


def list_hotkey_editor_modules() -> list[tuple[str, str, str]]:
    """设置页：常用模块 + 用户已配置但不在常用表中的项（不铺全菜单）。"""
    configured = get_configured_module_shortcuts()
    names = _menu_name_map()
    seen: set[str] = set()
    out: list[tuple[str, str, str]] = []
    for mid in _HOTKEY_EDITOR_CURATED:
        if not mid or mid in seen:
            continue
        seen.add(mid)
        out.append((mid, names.get(mid, mid), get_module_shortcut(mid)))
    for mid in sorted(configured.keys()):
        if mid in seen:
            continue
        seen.add(mid)
        out.append((mid, names.get(mid, mid), configured[mid]))
    return out


def list_hotkey_picker_modules() -> list[tuple[str, str]]:
    """添加模块下拉：侧栏可见且已迁移的项。"""
    from services.menu_registry import visible_menu_items

    rows: list[tuple[str, str]] = []
    for item in visible_menu_items():
        mid = str(item.get("id") or "").strip()
        if not mid or mid in ("__about__",):
            continue
        if not is_migrated(mid):
            continue
        rows.append((mid, str(item.get("name") or mid)))
    rows.sort(key=lambda x: x[1])
    return rows


# 不进 RegisterHotKey：截图有独立 hotkeys.screenshot*；首页/沉浸仅应用前台
_GLOBAL_EXCLUDE_MODULES: frozenset[str] = frozenset(
    {
        "screenshot_tool",  # 与 Alt+A 捕获同键，勿改成「打开模块页」
        "home",  # Ctrl+H 仅应用级，禁止全局抢走浏览器历史等
        "column_preview",  # F11 沉浸由 toggle_fullscreen 处理
    }
)


def global_module_bindings() -> dict[str, str]:
    """需 RegisterHotKey 的模块：seq -> module_id（带 Alt/Ctrl 修饰）。

    同键先到先得；调用方应先写入截图键，再合并本表并跳过已占用键。
    """
    out: dict[str, str] = {}
    for mid, _name, seq in list_shortcut_modules():
        if not seq or mid in _GLOBAL_EXCLUDE_MODULES:
            continue
        upper = seq.upper()
        if "ALT" not in upper and "CTRL" not in upper and "META" not in upper:
            continue
        if mid in out.values():
            continue
        if seq in out:
            continue
        out[seq] = mid
    return out
