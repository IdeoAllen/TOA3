# -*- coding: utf-8 -*-
"""高清矢量图标（SVG → QIcon，HiDPI 感知渲染）。"""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QColor, QPainter, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer

from services.config_service import project_root

ICON_DIR = project_root() / "resources" / "icons" / "svg"

_ALIAS: dict[str, str] = {
    # 壳 / 顶栏
    "system_settings": "settings",
    "main_window": "main_window",
    "job_scheduler": "clock",
    "user_extensions": "package",
    "notifications": "notifications",
    "settings": "settings_svg",
    "theme": "theme_svg",
    "theme_preview": "theme_svg",
    "palette": "theme_svg",
    "about": "about",
    "exit": "exit",
    "restart": "restart",
    "fullscreen": "fullscreen_svg",
    "immersive": "fullscreen_svg",
    "home": "home",
    "user": "user",
    "switch_user": "list",
    # 办公
    "web_workspace": "web_workspace",
    "quick_notepad": "quick_notepad",
    "quadrant_tasks": "quadrant_tasks",
    "pomodoro": "pomodoro",
    "clock": "pomodoro",
    "screenshot_tool": "camera",
    "camera": "camera",
    "ocr_tool": "ocr_tool",
    "clipboard_history": "clipboard_history",
    "llm_assistant": "llm_assistant",
    "harness_agent": "harness_agent",
    # 图片
    "image": "image",
    "image_creator": "image_creator",
    "image_adjust": "image_adjust",
    "watermark_photo_generator": "watermark_photo",
    "watermark_photo": "watermark_photo",
    "image_watermark": "image_watermark",
    "image_to_scan": "image_to_scan",
    "image_format_convert": "image_format_convert",
    "watermark_remover": "watermark_remover",
    "photo_extractor": "photo_extractor",
    # 目录 / 文件
    "folder": "folder",
    "folder-open": "folder_open",
    "folder_open": "folder_open",
    "directory_inspector": "directory_inspector",
    "deliverable_directory_check": "directory_inspector",
    "column_preview": "column_preview",
    "directory_generator": "directory_generator",
    "batch_rename": "batch_rename",
    "enhanced_directory_inspector": "package",
    "package": "package",
    "file_packager": "package",
    # 文档 / 表格
    "file-text": "file_text",
    "file_text": "file_text",
    "document_composer": "document_composer",
    "pdf_toolkit": "pdf_toolkit",
    "excel_cleaner": "excel_cleaner",
    "excel_row_to_column": "row_to_column",
    "table": "table",
    "row_to_column": "row_to_column",
    "table_card_generator": "table_card_generator",
    "generic_generator": "generic_generator",
    "generic_generator_simple": "generic_generator",
    # 业务
    "teaching_assistant_resume": "resume_generator",
    "resume_generator": "resume_generator",
    "resume_extractor": "resume_extractor",
    "schedule_reminder": "schedule_reminder",
    "schedule_format_converter": "calendar",
    "calendar": "calendar",
    "deduction_note_formatter": "deduction_note_formatter",
    "list": "list",
}

_CACHE: dict[tuple[str, str, int, float], QIcon] = {}


def _resolve_name(name: str) -> str:
    raw = str(name or "").strip().lower()
    mapped = _ALIAS.get(raw, raw).replace("-", "_")
    candidates = [
        f"{mapped}_svg.svg",
        f"{mapped}.svg",
        f"{raw}_svg.svg",
        f"{raw}.svg",
    ]
    for c in candidates:
        p = ICON_DIR / c
        if p.is_file():
            return c
    return ""


def svg_path(name: str) -> Path | None:
    file = _resolve_name(name)
    if not file:
        return None
    return ICON_DIR / file


def device_pixel_ratio(parent=None) -> float:
    """当前窗口/屏幕的设备像素比（125%/150%/200% 缩放）。"""
    widget = parent
    if widget is not None:
        try:
            window = widget.window() if hasattr(widget, "window") else widget
            scr = window.screen() if window is not None and hasattr(window, "screen") else None
            if scr is not None and hasattr(scr, "devicePixelRatio"):
                return float(scr.devicePixelRatio())
        except (RuntimeError, AttributeError, TypeError):
            pass
    app = QGuiApplication.instance()
    if app is not None:
        try:
            scr = app.primaryScreen()
            if scr is not None and hasattr(scr, "devicePixelRatio"):
                return float(scr.devicePixelRatio())
        except (RuntimeError, AttributeError, TypeError):
            pass
    return 1.0


def hi_dpi_pixmap(
    image_path: Path | str,
    logical_w: int,
    logical_h: int,
    *,
    parent=None,
) -> QPixmap:
    """栅格图 Logo 等：按设备像素比缩放，避免顶栏模糊。"""
    dpr = max(device_pixel_ratio(parent), 1.0)
    src = QPixmap(str(image_path))
    if src.isNull():
        return src
    physical_w = max(1, int(round(logical_w * dpr)))
    physical_h = max(1, int(round(logical_h * dpr)))
    # 避免把小图硬放大导致模糊
    if src.width() >= physical_w or src.height() >= physical_h:
        scaled = src.scaled(
            physical_w,
            physical_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    else:
        scaled = src
    scaled.setDevicePixelRatio(dpr)
    return scaled


def _render_svg_to_pixmap(text: str, logical_w: int, logical_h: int, dpr: float) -> QPixmap:
    dpr = max(float(dpr), 1.0)
    logical_w = max(int(logical_w), 1)
    logical_h = max(int(logical_h), 1)
    physical_w = max(1, int(round(logical_w * dpr)))
    physical_h = max(1, int(round(logical_h * dpr)))

    renderer = QSvgRenderer(QByteArray(text.encode("utf-8")))
    if not renderer.isValid():
        return QPixmap()

    # 按物理像素绘制 SVG，再标记 DPR，避免逻辑坐标二次缩放发糊
    pm = QPixmap(physical_w, physical_h)
    pm.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(painter, QRectF(0, 0, physical_w, physical_h))
    painter.end()
    pm.setDevicePixelRatio(dpr)
    return pm


# 菜单 / 顶栏：统一 stroke，视觉重量一致
_UI_STROKE = "1.8"


def _normalize_ui_svg(svg_text: str) -> str:
    """统一 stroke-width / linecap，避免侧栏与顶栏粗细不一。"""
    out = re.sub(
        r'stroke-width="[^"]*"',
        f'stroke-width="{_UI_STROKE}"',
        svg_text,
    )
    if "stroke-linecap=" not in out:
        out = out.replace("<svg ", '<svg stroke-linecap="round" stroke-linejoin="round" ', 1)
    return out


# 兼容旧名
_normalize_header_svg = _normalize_ui_svg
_HEADER_STROKE = _UI_STROKE

def brand_logo_pixmap(
    logical_w: int,
    logical_h: int,
    *,
    parent=None,
) -> QPixmap:
    """品牌 Logo：优先 SVG 矢量，其次高清位图 HiDPI 缩放。"""
    from services.system_info import logo_path

    path = logo_path()
    if path is None:
        return QPixmap()
    dpr = device_pixel_ratio(parent)
    if path.suffix.lower() == ".svg":
        try:
            return _render_svg_to_pixmap(path.read_text(encoding="utf-8"), logical_w, logical_h, dpr)
        except OSError:
            return QPixmap()
    return hi_dpi_pixmap(path, logical_w, logical_h, parent=parent)


def _tint_svg(svg_text: str, color: str) -> str:
    c = color.strip()
    out = re.sub(r"stroke=\"[^\"]*\"", f'stroke="{c}"', svg_text)
    out = re.sub(r"stroke='[^']*'", f"stroke='{c}'", out)
    out = re.sub(r"fill=\"(?!none)[^\"]*\"", f'fill="{c}"', out)
    return out


def _render_svg_icon(text: str, logical_size: int, dpr: float) -> QIcon:
    """将 SVG 按物理像素光栅化并登记多档 DPR，避免模糊/锯齿。"""
    dpr = max(float(dpr), 1.0)
    logical_size = max(int(logical_size), 1)
    icon = QIcon()
    # 当前屏 + 常见缩放档，跨屏拖动仍清晰
    ratios = sorted({1.0, 1.25, 1.5, 2.0, 3.0, round(dpr, 2)})
    for r in ratios:
        pm = _render_svg_to_pixmap(text, logical_size, logical_size, r)
        if not pm.isNull():
            icon.addPixmap(pm)
    return icon


_CHEVRON_POINTS: dict[str, list[tuple[float, float]]] = {
    "left": [(16.0, 4.0), (8.0, 12.0), (16.0, 20.0)],
    "right": [(8.0, 4.0), (16.0, 12.0), (8.0, 20.0)],
    "up": [(4.0, 16.0), (12.0, 7.5), (20.0, 16.0)],
    "down": [(4.0, 8.0), (12.0, 16.5), (20.0, 8.0)],
}


def chevron_icon(
    direction: str,
    *,
    color: str,
    size: int = 14,
    parent=None,
) -> QIcon:
    """主题色 chevron（月历导航 / 控件箭头），程序化绘制避免 Windows 系统绿圆按钮。"""
    dpr = device_pixel_ratio(parent)
    key = ("chevron", direction, color.strip(), size, round(dpr, 2))
    if key in _CACHE:
        return _CACHE[key]

    points = _CHEVRON_POINTS.get(direction)
    if not points:
        return QIcon()

    stroke = color.strip() or "#FFFFFF"
    icon = QIcon()
    ratios = sorted({1.0, 1.25, 1.5, 2.0, 3.0, round(dpr, 2)})
    for ratio in ratios:
        logical = max(int(size), 1)
        physical = max(1, int(round(logical * ratio)))
        pm = QPixmap(physical, physical)
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor(stroke))
        pen.setWidthF(max(1.6, 2.6 * (physical / 24.0)))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        scale = physical / 24.0
        painter.drawPolyline([QPointF(x * scale, y * scale) for x, y in points])
        painter.end()
        pm.setDevicePixelRatio(ratio)
        icon.addPixmap(pm)

    _CACHE[key] = icon
    return icon


def get_icon(
    name: str,
    *,
    color: str | None = None,
    size: int = 20,
    parent=None,
    normalize_stroke: bool = True,
) -> QIcon:
    """加载 SVG 矢量图标；color 用于侧栏/顶栏着色。"""
    raw = str(name or "").strip().lower()
    # 方向箭头 / 全屏：无 SVG 时程序绘制，避免顶栏空白
    if raw in ("left", "right", "up", "down"):
        return chevron_icon(raw, color=color or "#FFFFFF", size=size, parent=parent)

    dpr = device_pixel_ratio(parent)
    key = (name, color or "", size, round(dpr, 2), normalize_stroke)
    if key in _CACHE:
        return _CACHE[key]

    path = svg_path(name)
    if path is None:
        return QIcon()

    text = path.read_text(encoding="utf-8")
    if normalize_stroke:
        text = _normalize_ui_svg(text)
    if color:
        text = _tint_svg(text, color)

    icon = _render_svg_icon(text, size, dpr)
    _CACHE[key] = icon
    return icon


def get_header_icon(
    name: str,
    *,
    color: str | None = None,
    size: int = 18,
    parent=None,
) -> QIcon:
    """顶栏专用：全部走 SVG，同尺寸、同 stroke，避免粗细不一。"""
    return get_icon(name, color=color, size=size, parent=parent, normalize_stroke=True)


def fullscreen_icon(*, color: str, size: int = 20, parent=None) -> QIcon:
    """兼容旧调用：优先 SVG。"""
    return get_icon("fullscreen", color=color, size=size, parent=parent)


def icon_pixmap(
    name: str,
    *,
    color: str | None = None,
    size: int = 20,
    parent=None,
) -> QPixmap:
    """直接取 HiDPI 位图（卡片/标签用）；禁止再对返回值做模糊缩放。"""
    dpr = device_pixel_ratio(parent)
    path = svg_path(name)
    if path is None:
        return QPixmap()
    text = path.read_text(encoding="utf-8")
    text = _normalize_ui_svg(text)
    if color:
        text = _tint_svg(text, color)
    return _render_svg_to_pixmap(text, size, size, dpr)


def menu_item_icon(
    menu_icon: str,
    *,
    for_nav: bool = True,
    size: int = 20,
    parent=None,
) -> QIcon:
    if for_nav:
        from app.app_state import AppState

        pal = AppState.get().palette or {}
        color = str(pal.get("nav_fg") or "#EAF0F8")
    else:
        color = "#FFFFFF"
    return get_icon(menu_icon, color=color, size=size, parent=parent, normalize_stroke=True)


def clear_cache() -> None:
    _CACHE.clear()


def app_window_icon(*, parent=None) -> QIcon:
    """任务栏 / 托盘 / 窗口图标：开发版橙 DEV / 正式版蓝 3.0。"""
    from services.app_branding import resolve_app_icon_ico, resolve_app_icon_png

    icon = QIcon()
    png = resolve_app_icon_png()
    if png is not None and png.is_file():
        src = QPixmap(str(png))
        if not src.isNull():
            for logical in (16, 24, 32, 48, 64, 128, 256):
                scaled = src.scaled(
                    logical,
                    logical,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                icon.addPixmap(scaled)
    ico = resolve_app_icon_ico()
    if ico is not None and ico.is_file():
        icon.addFile(str(ico))
    if icon.isNull() and ico is not None and ico.is_file():
        return QIcon(str(ico))
    return icon
