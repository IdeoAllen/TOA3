# -*- coding: utf-8 -*-
"""窗口规格：尺寸、边距、对话框标题（config/ui_spec.yml）。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from PySide6.QtGui import QGuiApplication, QScreen
from PySide6.QtWidgets import QDialog, QMainWindow, QWidget

ROOT = Path(__file__).resolve().parents[1]

_SPEC_CACHE: dict | None = None


def _load_spec(force: bool = False) -> dict:
    global _SPEC_CACHE
    if _SPEC_CACHE is not None and not force:
        return _SPEC_CACHE
    path = ROOT / "config" / "ui_spec.yml"
    if not path.is_file():
        _SPEC_CACHE = {}
        return _SPEC_CACHE
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    _SPEC_CACHE = data if isinstance(data, dict) else {}
    return _SPEC_CACHE


def _block(name: str) -> dict[str, Any]:
    return dict(_load_spec().get(name) or {})


def shell_spec() -> dict[str, Any]:
    return _block("shell")


def page_spec() -> dict[str, Any]:
    return _block("page")


def dialog_spec(kind: str) -> dict[str, Any]:
    dialogs = _block("dialogs")
    k = str(kind or "medium").strip().lower()
    if k == "login":
        k = "account"
    spec = dict(dialogs.get(k) or dialogs.get("medium") or {})
    return spec


def message_title(kind: str) -> str:
    messages = _block("message")
    key = f"{kind}_title"
    return str(messages.get(key) or messages.get("error_title") or "提示")


def apply_shell_spec(window: QMainWindow) -> None:
    spec = shell_spec()
    min_w = int(spec.get("min_width") or 800)
    min_h = int(spec.get("min_height") or 600)
    window.setMinimumSize(min_w, min_h)
    w = int(spec.get("default_width") or 1200)
    h = int(spec.get("default_height") or 800)
    window.resize(w, h)
    header_h = int(spec.get("header_height") or 48)
    nav_w = int(spec.get("nav_width") or 200)
    window.setProperty("toa_header_height", header_h)
    window.setProperty("toa_nav_width", nav_w)


def _screen_for(widget: QWidget) -> QScreen | None:
    parent = widget.parentWidget()
    if parent is not None:
        scr = parent.screen()
        if scr is not None:
            return scr
    handle = widget.windowHandle()
    if handle is not None and handle.screen() is not None:
        return handle.screen()
    return QGuiApplication.primaryScreen()


def center_on_screen(widget: QWidget) -> None:
    """弹窗相对屏幕可用区水平+垂直居中。"""
    screen = _screen_for(widget)
    if screen is None:
        return
    geo = screen.availableGeometry()
    fw = widget.frameGeometry().width() or widget.width()
    fh = widget.frameGeometry().height() or widget.height()
    if fw <= 0 or fh <= 0:
        hint = widget.sizeHint()
        fw = max(fw, hint.width())
        fh = max(fh, hint.height())
    x = geo.x() + max(0, (geo.width() - fw) // 2)
    y = geo.y() + max(0, (geo.height() - fh) // 2)
    widget.move(x, y)


def apply_dialog_spec(dialog: QDialog, kind: str = "medium") -> None:
    """登记规格；真正定宽高在 show 时 finalize_dialog_geometry（按内容+居中+禁止拉伸）。"""
    spec = dialog_spec(kind)
    dialog.setProperty("toa_dialog_kind", kind)
    try:
        dialog.setSizeGripEnabled(False)
    except Exception:
        pass
    pref_w = int(spec.get("width") or spec.get("min_width") or 480)
    dialog.setMinimumWidth(int(spec.get("min_width") or pref_w))
    dialog.resize(pref_w, int(spec.get("min_height") or 200))


def finalize_dialog_geometry(dialog: QDialog, kind: str | None = None) -> None:
    """按内容计算尺寸并固定，禁止用户拖拽改大小；再屏幕居中。"""
    kind = kind or str(dialog.property("toa_dialog_kind") or "medium")
    spec = dialog_spec(kind)
    lay = dialog.layout()
    if lay is not None:
        lay.activate()

    min_w = int(spec.get("min_width") or 360)
    min_h = int(spec.get("min_height") or 160)
    pref_w = int(spec.get("width") or min_w)

    screen = _screen_for(dialog)
    max_w, max_h = 1200, 900
    if screen is not None:
        geo = screen.availableGeometry()
        max_w = max(min_w, int(geo.width() * 0.92))
        max_h = max(min_h, int(geo.height() * 0.88))

    # 先定宽，再测高度（多行文案依赖宽度）
    w = min(max(min_w, pref_w), max_w)
    dialog.setFixedWidth(w)
    if lay is not None:
        lay.activate()
    dialog.adjustSize()
    from PySide6.QtWidgets import QGroupBox, QLineEdit

    group_extra = 14 * len(dialog.findChildren(QGroupBox))
    field_extra = 2 * max(0, len(dialog.findChildren(QLineEdit)) - 1)
    hint_h = max(dialog.sizeHint().height(), dialog.minimumSizeHint().height())
    hint_h += 8 + group_extra + field_extra
    h = min(max(min_h, hint_h), max_h)
    dialog.setFixedSize(w, h)
    try:
        dialog.setSizeGripEnabled(False)
    except Exception:
        pass
    center_on_screen(dialog)


def apply_page_layout(widget: QWidget) -> None:
    """若根布局为 QVBoxLayout/QHBoxLayout，应用统一 margin/spacing。"""
    lay = widget.layout()
    if lay is None:
        return
    spec = page_spec()
    m = int(spec.get("margin") or 20)
    s = int(spec.get("spacing") or 12)
    lay.setContentsMargins(m, m, m, m)
    lay.setSpacing(s)


def page_content_margins() -> tuple[int, int, int, int]:
    m = int(page_spec().get("margin") or 20)
    return (m, m, m, m)
