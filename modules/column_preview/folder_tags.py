# -*- coding: utf-8 -*-
"""文件夹彩色标签（对标 Finder Labels），本地 JSON 持久化。"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap

from services.storage_paths import module_data_dir

logger = logging.getLogger(__name__)

# Finder 风格标签色（语义色，非界面主题硬编码）
TAG_COLORS: dict[str, tuple[str, str]] = {
    "red": ("红", "#FF3B30"),
    "orange": ("橙", "#FF9500"),
    "yellow": ("黄", "#FFCC00"),
    "green": ("绿", "#34C759"),
    "blue": ("蓝", "#007AFF"),
    "purple": ("紫", "#AF52DE"),
    "gray": ("灰", "#8E8E93"),
}

_TAGS_FILE = "folder_tags.json"


def path_key(path: Path) -> str:
    """Windows 下统一大小写与绝对路径，避免标签对不上。"""
    import os

    try:
        return os.path.normcase(str(path.resolve()))
    except OSError:
        return os.path.normcase(str(Path(path).absolute()))


def _tags_path() -> Path:
    return module_data_dir("column_preview", create=True) / _TAGS_FILE


def load_tags() -> dict[str, str]:
    path = _tags_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            out: dict[str, str] = {}
            for k, v in data.items():
                if v not in TAG_COLORS:
                    continue
                out[path_key(Path(str(k)))] = str(v)
            return out
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("load folder tags failed: %s", e)
    return {}


def save_tags(tags: dict[str, str]) -> None:
    path = _tags_path()
    cleaned = {path_key(Path(k)): v for k, v in tags.items() if v in TAG_COLORS}
    path.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")


def tag_color(key: str | None) -> QColor | None:
    if not key or key not in TAG_COLORS:
        return None
    return QColor(TAG_COLORS[key][1])


def tag_dot_pixmap(key: str, size: int = 12, *, dpr: float = 1.0) -> QPixmap:
    color = tag_color(key)
    if color is None:
        return QPixmap()
    px = max(1, int(size * dpr))
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(color)
    p.setPen(Qt.PenStyle.NoPen)
    margin = max(1, int(1 * dpr))
    p.drawEllipse(margin, margin, px - 2 * margin, px - 2 * margin)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def _draw_mac_colored_folder(logical_size: int, tag_key: str, *, dpr: float = 1.0) -> QPixmap:
    """macOS 风格：整枚文件夹用标签色填充。"""
    color = tag_color(tag_key)
    if color is None:
        return QPixmap()
    px = max(16, int(logical_size * dpr))
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)

    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    m = px * 0.10
    w = px - 2 * m
    h = px - 2 * m
    tab_h = h * 0.24
    tab_w = w * 0.46
    body_y = m + tab_h * 0.62
    body_h = h - (body_y - m)
    radius = max(2.0, px * 0.06)

    tab_path = QPainterPath()
    tab_path.addRoundedRect(m, m, tab_w, tab_h, radius * 0.7, radius * 0.7)
    body_path = QPainterPath()
    body_path.addRoundedRect(m, body_y, w, body_h, radius, radius)
    folder_path = tab_path.united(body_path)

    base = QColor(color)
    tab_fill = base.darker(112)
    body_fill = base.lighter(106)
    front = base.darker(125)

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(body_fill)
    p.drawPath(body_path)
    p.setBrush(tab_fill)
    p.drawPath(tab_path)

    fold_x = m + w * 0.58
    fold_path = QPainterPath()
    fold_path.moveTo(fold_x, body_y + body_h * 0.08)
    fold_path.lineTo(m + w * 0.92, body_y + body_h * 0.08)
    fold_path.lineTo(m + w * 0.92, body_y + body_h * 0.42)
    fold_path.lineTo(fold_x, body_y + body_h * 0.42)
    fold_path.closeSubpath()
    p.setBrush(front)
    p.drawPath(fold_path)

    p.setPen(QPen(base.darker(140), max(1.0, dpr * 0.8)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(folder_path)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def folder_pixmap_with_tag(
    base: QPixmap, tag_key: str | None, *, dpr: float = 1.0
) -> QPixmap:
    """兼容旧接口：返回 macOS 风格文件夹图标。"""
    from modules.column_preview.finder_icons import finder_folder_pixmap

    logical = max(16, int(round(base.width() / max(dpr, 1.0)))) if not base.isNull() else 64
    return finder_folder_pixmap(logical, tag_key, dpr=dpr)
