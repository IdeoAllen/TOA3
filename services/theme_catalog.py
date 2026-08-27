# -*- coding: utf-8 -*-
"""官方主题目录（与 TOA2 common/theme_catalog.PRODUCT_THEMES 对齐）。"""
from __future__ import annotations

from app.theme_loader import DEFAULT_THEME, theme_json_path, theme_display_name

# 保留 JSON/QSS，不进入设置下拉（与官方主题过于相近或仅开发参考）
HIDDEN_THEMES: tuple[str, ...] = (
    "toa_complete",  # 控件库完整色板，主色与 dms_blue 同源
    "pure_black",  # OLED 纯黑，与 dms_black 同属暗色蓝系
)

# id → 展示名（顺序即系统设置下拉顺序：默认 → 浅色办公 → 浅色个性 → 深色）
OFFICIAL_THEMES: tuple[tuple[str, str], ...] = (
    # 默认 / 品牌
    ("dms_blue", "商务蓝"),
    # 浅色 · 办公
    ("dms_white", "素白"),
    ("office_2019_colorful", "Office 2019 彩色"),
    ("vs2019_blue", "VS2019 经典蓝"),
    # 浅色 · 个性
    ("dms_green", "青碧"),
    ("dms_copper", "古铜"),
    # 深色
    ("dms_black", "墨黑·霓虹蓝"),
    ("wxi_dark", "WXI 紫暗"),
    ("deep_dark", "深棕·暖暗"),
)

# 旧 ttkbootstrap 壳主题（TOA2 可选，尚无 JSON 令牌文件，TOA3 MVP 不纳入下拉）
LEGACY_BOOT_THEMES: tuple[tuple[str, str], ...] = (
    ("journal", "红"),
    ("minty", "绿"),
    ("cosmo", "蓝"),
    ("pulse", "紫"),
)


def official_theme_ids() -> list[str]:
    return [tid for tid, _ in OFFICIAL_THEMES]


def selectable_themes() -> list[tuple[str, str]]:
    """返回 [(id, 展示名)]，仅含已同步 JSON 的官方主题。"""
    out: list[tuple[str, str]] = []
    for tid, fallback_label in OFFICIAL_THEMES:
        if theme_json_path(tid).is_file():
            label = theme_display_name(tid)
            if label == tid:
                label = fallback_label
            out.append((tid, label))
    return out


def canonicalize_theme(theme_id: str | None) -> str:
    raw = str(theme_id or "").strip()
    if not raw:
        return DEFAULT_THEME
    if theme_json_path(raw).is_file():
        return raw
    return DEFAULT_THEME


def theme_description(theme_id: str) -> str:
    path = theme_json_path(theme_id)
    if not path.is_file():
        return ""
    try:
        import json

        doc = json.loads(path.read_text(encoding="utf-8"))
        return str(doc.get("description") or "")
    except Exception:
        return ""
