# -*- coding: utf-8 -*-
"""macOS Finder 风格文件夹 / 文件图标（HiDPI 矢量绘制）。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QColor,
    QImageReader,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

from modules.column_preview.folder_tags import TAG_COLORS, tag_color
from services.office_preview import OFFICE_EXTENSIONS

_IMAGE_EXT = {
    ".png",
    ".jpg",
    ".jpeg",
    ".jfif",
    ".bmp",
    ".gif",
    ".webp",
    ".tif",
    ".tiff",
    ".ico",
    ".svg",
    ".svgz",
}
_PDF_EXT = {".pdf"}

_DOC_BLUE = "#2B579A"
_XLS_GREEN = "#217346"
_PPT_ORANGE = "#D24726"
_PDF_RED = "#E34C26"
_PAGE = "#F7F8FA"
_PAGE_EDGE = "#C8CDD4"


def finder_folder_pixmap(
    logical_size: int, tag_key: str | None = None, *, dpr: float = 1.0
) -> QPixmap:
    """macOS 文件夹：默认蓝色渐变；有标签时为整枚彩色文件夹。"""
    if tag_key and tag_key in TAG_COLORS:
        return _draw_tagged_folder(logical_size, tag_key, dpr=dpr)
    return _draw_default_folder(logical_size, dpr=dpr)


def finder_file_pixmap(
    path: Path,
    logical_size: int,
    *,
    dpr: float = 1.0,
    allow_thumb: bool = False,
    parent=None,
) -> QPixmap:
    """按扩展名绘制 macOS 风格文件图标；图标模式可对图片显示缩略图。"""
    ext = path.suffix.lower()
    if allow_thumb and ext in _IMAGE_EXT and path.is_file():
        # 解码边长按物理像素，保证 HiDPI 下封面清晰
        edge = max(256, int(logical_size * max(dpr, 1.0) * 2))
        thumb = _load_image_thumb(path, parent=parent, max_edge=edge)
        if thumb is not None and not thumb.isNull():
            return _draw_image_icon(thumb, logical_size, dpr=dpr)
    if ext in _PDF_EXT:
        return _draw_typed_doc(logical_size, "PDF", _PDF_RED, dpr=dpr)
    if ext in {".doc", ".docx", ".rtf"}:
        return _draw_typed_doc(logical_size, "DOC", _DOC_BLUE, dpr=dpr)
    if ext in {".xls", ".xlsx", ".xlsm", ".csv"}:
        return _draw_typed_doc(logical_size, "XLS", _XLS_GREEN, dpr=dpr)
    if ext in {".ppt", ".pptx", ".pps", ".ppsx"}:
        return _draw_typed_doc(logical_size, "PPT", _PPT_ORANGE, dpr=dpr)
    if ext in OFFICE_EXTENSIONS:
        return _draw_typed_doc(logical_size, "DOC", _DOC_BLUE, dpr=dpr)
    if ext in _IMAGE_EXT:
        return _draw_typed_doc(logical_size, "IMG", "#5856D6", dpr=dpr)
    if ext in {".zip", ".rar", ".7z", ".tar", ".gz"}:
        return _draw_typed_doc(logical_size, "ZIP", "#8E8E93", dpr=dpr)
    return _draw_generic_doc(logical_size, dpr=dpr)


def _px(logical_size: int, dpr: float) -> int:
    return max(16, int(logical_size * dpr))


def _draw_default_folder(logical_size: int, *, dpr: float = 1.0) -> QPixmap:
    px = _px(logical_size, dpr)
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    m = px * 0.08
    w = px - 2 * m
    h = px - 2 * m
    tab_h = h * 0.26
    tab_w = w * 0.48
    body_y = m + tab_h * 0.58
    body_h = h - (body_y - m)
    radius = max(2.5, px * 0.065)

    tab_path = QPainterPath()
    tab_path.addRoundedRect(m, m + px * 0.01, tab_w, tab_h, radius * 0.65, radius * 0.65)
    body_path = QPainterPath()
    body_path.addRoundedRect(m, body_y, w, body_h, radius, radius)
    folder_path = tab_path.united(body_path)

    body_grad = QLinearGradient(m, body_y, m, body_y + body_h)
    body_grad.setColorAt(0.0, QColor("#69B4FF"))
    body_grad.setColorAt(0.45, QColor("#1A92FF"))
    body_grad.setColorAt(1.0, QColor("#0070E0"))

    tab_grad = QLinearGradient(m, m, m, m + tab_h)
    tab_grad.setColorAt(0.0, QColor("#B8DCFF"))
    tab_grad.setColorAt(1.0, QColor("#7EC3FF"))

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(body_grad)
    p.drawPath(body_path)
    p.setBrush(tab_grad)
    p.drawPath(tab_path)

    fold_x = m + w * 0.56
    fold_path = QPainterPath()
    fold_path.moveTo(fold_x, body_y + body_h * 0.06)
    fold_path.lineTo(m + w * 0.94, body_y + body_h * 0.06)
    fold_path.lineTo(m + w * 0.94, body_y + body_h * 0.40)
    fold_path.lineTo(fold_x, body_y + body_h * 0.40)
    fold_path.closeSubpath()
    p.setBrush(QColor("#0060C7"))
    p.drawPath(fold_path)

    shine = QLinearGradient(m, body_y, m + w, body_y + body_h * 0.35)
    shine.setColorAt(0.0, QColor(255, 255, 255, 70))
    shine.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(shine)
    p.drawPath(body_path)

    p.setPen(QPen(QColor(0, 70, 160, 90), max(1.0, dpr * 0.75)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(folder_path)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def _draw_tagged_folder(logical_size: int, tag_key: str, *, dpr: float = 1.0) -> QPixmap:
    color = tag_color(tag_key)
    if color is None:
        return _draw_default_folder(logical_size, dpr=dpr)
    px = _px(logical_size, dpr)
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    m = px * 0.08
    w = px - 2 * m
    h = px - 2 * m
    tab_h = h * 0.26
    tab_w = w * 0.48
    body_y = m + tab_h * 0.58
    body_h = h - (body_y - m)
    radius = max(2.5, px * 0.065)

    tab_path = QPainterPath()
    tab_path.addRoundedRect(m, m + px * 0.01, tab_w, tab_h, radius * 0.65, radius * 0.65)
    body_path = QPainterPath()
    body_path.addRoundedRect(m, body_y, w, body_h, radius, radius)
    folder_path = tab_path.united(body_path)

    base = QColor(color)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(base.lighter(108))
    p.drawPath(body_path)
    p.setBrush(base.darker(108))
    p.drawPath(tab_path)

    fold_x = m + w * 0.56
    fold_path = QPainterPath()
    fold_path.moveTo(fold_x, body_y + body_h * 0.06)
    fold_path.lineTo(m + w * 0.94, body_y + body_h * 0.06)
    fold_path.lineTo(m + w * 0.94, body_y + body_h * 0.40)
    fold_path.lineTo(fold_x, body_y + body_h * 0.40)
    fold_path.closeSubpath()
    p.setBrush(base.darker(125))
    p.drawPath(fold_path)

    shine = QLinearGradient(m, body_y, m + w, body_y + body_h * 0.3)
    shine.setColorAt(0.0, QColor(255, 255, 255, 55))
    shine.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(shine)
    p.drawPath(body_path)

    p.setPen(QPen(base.darker(135), max(1.0, dpr * 0.75)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(folder_path)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def _page_path(logical_size: float, px: int) -> tuple[QPainterPath, QPainterPath, float]:
    m = px * 0.14
    w = px - 2 * m
    h = px - 2 * m
    fold = w * 0.28
    radius = max(2.0, px * 0.06)
    page = QPainterPath()
    page.addRoundedRect(m, m, w - fold * 0.35, h, radius, radius)
    corner = QPainterPath()
    corner.moveTo(m + w - fold, m)
    corner.lineTo(m + w, m)
    corner.lineTo(m + w, m + fold)
    corner.closeSubpath()
    return page, corner, fold


def _draw_generic_doc(logical_size: int, *, dpr: float = 1.0) -> QPixmap:
    px = _px(logical_size, dpr)
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    page, corner, _fold = _page_path(logical_size, px)

    shadow = QPainterPath()
    shadow.addRoundedRect(px * 0.15, px * 0.16, px * 0.72, px * 0.72, px * 0.06, px * 0.06)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 28))
    p.drawPath(shadow)

    grad = QLinearGradient(0, px * 0.12, 0, px * 0.88)
    grad.setColorAt(0, QColor("#FFFFFF"))
    grad.setColorAt(1, QColor(_PAGE))
    p.setBrush(grad)
    p.setPen(QPen(QColor(_PAGE_EDGE), max(1.0, dpr * 0.6)))
    p.drawPath(page)
    p.setBrush(QColor("#E3E6EA"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawPath(corner)

    line_y = px * 0.42
    p.setPen(QPen(QColor("#D1D5DB"), max(1.0, dpr * 0.55)))
    for i in range(3):
        y = line_y + i * px * 0.11
        p.drawLine(int(px * 0.24), int(y), int(px * 0.62), int(y))
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def _draw_typed_doc(logical_size: int, label: str, badge: str, *, dpr: float = 1.0) -> QPixmap:
    px = _px(logical_size, dpr)
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    page, corner, _fold = _page_path(logical_size, px)

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 24))
    p.drawRoundedRect(int(px * 0.15), int(px * 0.16), int(px * 0.7), int(px * 0.72), int(px * 0.06), int(px * 0.06))

    grad = QLinearGradient(0, px * 0.12, 0, px * 0.88)
    grad.setColorAt(0, QColor("#FFFFFF"))
    grad.setColorAt(1, QColor(_PAGE))
    p.setBrush(grad)
    p.setPen(QPen(QColor(_PAGE_EDGE), max(1.0, dpr * 0.6)))
    p.drawPath(page)
    p.setBrush(QColor("#E3E6EA"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawPath(corner)

    badge_h = px * 0.22
    badge_w = px * 0.52
    badge_x = px * 0.5 - badge_w / 2
    badge_y = px * 0.62
    badge_path = QPainterPath()
    badge_path.addRoundedRect(badge_x, badge_y, badge_w, badge_h, px * 0.04, px * 0.04)
    p.setBrush(QColor(badge))
    p.drawPath(badge_path)

    from PySide6.QtGui import QFont

    font = QFont("Segoe UI")
    font.setBold(True)
    font.setPixelSize(max(7, int(px * 0.16)))
    p.setFont(font)
    p.setPen(QColor("#FFFFFF"))
    p.drawText(
        int(badge_x),
        int(badge_y),
        int(badge_w),
        int(badge_h),
        int(Qt.AlignmentFlag.AlignCenter),
        label[:3],
    )
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def _load_image_thumb(path: Path, *, parent=None, max_edge: int = 512) -> QPixmap | None:
    """解码缩略图；返回物理像素 pixmap（不设 DPR），供图标绘制按像素贴图。"""
    del parent  # 保留签名兼容调用方
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid() and (size.width() > max_edge or size.height() > max_edge):
        if size.width() >= size.height():
            reader.setScaledSize(size * (max_edge / size.width()))
        else:
            reader.setScaledSize(size * (max_edge / size.height()))
    img = reader.read()
    if img.isNull():
        return None
    return QPixmap.fromImage(img)


def _draw_image_icon(source: QPixmap, logical_size: int, *, dpr: float = 1.0) -> QPixmap:
    """Finder 相册式：圆角方框内 cover 裁切铺满，避免白边小图。

    注意：目标 pixmap 以物理像素绘制；中间图不设 DPR，避免 HiDPI 下
    drawPixmap 逻辑坐标错位导致「大白框 + 角落小图」。
    """
    px = _px(logical_size, dpr)
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    # 略收边，图标仍清晰；不再留大块白边
    margin = max(2.0, px * 0.04)
    side = px - 2 * margin
    radius = max(3.0, px * 0.12)

    # 轻阴影
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 32))
    p.drawRoundedRect(
        int(margin + dpr),
        int(margin + dpr * 1.2),
        int(side),
        int(side),
        int(radius),
        int(radius),
    )

    clip = QPainterPath()
    clip.addRoundedRect(margin, margin, side, side, radius, radius)
    p.setClipPath(clip)

    # 源图按物理像素；cover 铺满圆角区
    src = source
    if src.devicePixelRatio() and src.devicePixelRatio() != 1.0:
        # 若上游误设了 DPR，按物理尺寸重解一份，避免二次缩放错位
        src = QPixmap(source)
        src.setDevicePixelRatio(1.0)
    sw = max(1, src.width())
    sh = max(1, src.height())
    scale = max(side / sw, side / sh)
    tw = max(1, int(sw * scale + 0.5))
    th = max(1, int(sh * scale + 0.5))
    scaled = src.scaled(
        tw,
        th,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    dx = int(margin + (side - scaled.width()) / 2)
    dy = int(margin + (side - scaled.height()) / 2)
    p.drawPixmap(dx, dy, scaled)

    p.setClipping(False)
    p.setPen(QPen(QColor(0, 0, 0, 48), max(1.0, dpr * 0.7)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(int(margin), int(margin), int(side), int(side), int(radius), int(radius))
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm
