# -*- coding: utf-8 -*-
"""消息对话框状态图标（对标 WinForms MessageBox，见色知意）。"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap

# WinForms / Windows 常见语义色（固定，不跟主题漂，保证「见图知意」）
_COLORS = {
    "info": QColor("#0078D4"),  # 蓝 · 信息 i
    "warning": QColor("#F0A020"),  # 琥珀 · 警告 !
    "error": QColor("#E81123"),  # 红 · 错误 ×
    "confirm": QColor("#0078D4"),  # 蓝 · 确认 ?
    "success": QColor("#107C10"),  # 绿 · 成功 ✓
}


def _draw_circle_glyph(p: QPainter, r: QRectF, *, color: QColor) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawEllipse(r)


def _draw_circle_outline(p: QPainter, r: QRectF) -> None:
    pen = QPen(QColor(255, 255, 255, 180))
    pen.setWidthF(1.2)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(r.adjusted(0.5, 0.5, -0.5, -0.5))


def _draw_error_x(p: QPainter, logical: int) -> None:
    """几何对称红叉，不用字体乘号（避免偏斜）。"""
    pad = logical * 0.28
    x1, y1 = pad, pad
    x2, y2 = logical - pad, logical - pad
    pen = QPen(QColor("#FFFFFF"))
    pen.setWidthF(max(2.2, logical * 0.11))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    p.drawLine(QPointF(x2, y1), QPointF(x1, y2))


def _draw_success_check(p: QPainter, logical: int) -> None:
    """几何对称绿勾，不用字体符号。"""
    path = QPainterPath()
    path.moveTo(logical * 0.24, logical * 0.52)
    path.lineTo(logical * 0.40, logical * 0.68)
    path.lineTo(logical * 0.76, logical * 0.30)
    pen = QPen(QColor("#FFFFFF"))
    pen.setWidthF(max(2.4, logical * 0.12))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.drawPath(path)


def _draw_text_glyph(p: QPainter, r: QRectF, glyph: str, *, logical: int) -> None:
    font = QFont("Segoe UI", max(11, int(logical * 0.48)))
    font.setBold(True)
    p.setFont(font)
    p.setPen(QColor("#FFFFFF"))
    # 问号略上移，补偿字体基线
    box = QRectF(r)
    if glyph == "?":
        box.adjust(0, -1, 0, -1)
    elif glyph == "i":
        box.adjust(0, 0, 0, 1)
    p.drawText(box, int(Qt.AlignmentFlag.AlignCenter), glyph)


def message_status_pixmap(kind: str, *, logical: int = 40, dpr: float = 1.0) -> QPixmap:
    """绘制圆形/三角状态图标。"""
    key = kind if kind in _COLORS else "info"
    color = _COLORS[key]
    dpr = max(1.0, float(dpr))
    px = max(16, int(round(logical * dpr)))
    pix = QPixmap(px, px)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.scale(dpr, dpr)
    r = QRectF(1.5, 1.5, logical - 3.0, logical - 3.0)

    if key == "warning":
        path = QPainterPath()
        path.moveTo(QPointF(logical / 2, 2.5))
        path.lineTo(QPointF(logical - 3.0, logical - 3.0))
        path.lineTo(QPointF(3.0, logical - 3.0))
        path.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawPath(path)
        font = QFont("Segoe UI", max(10, int(logical * 0.42)))
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(QRectF(0, 2, logical, logical - 4), int(Qt.AlignmentFlag.AlignCenter), "!")
        pen = QPen(QColor(255, 255, 255, 180))
        pen.setWidthF(1.2)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
    else:
        _draw_circle_glyph(p, r, color=color)
        if key == "error":
            _draw_error_x(p, logical)
        elif key == "success":
            _draw_success_check(p, logical)
        else:
            glyph = "?" if key == "confirm" else "i"
            _draw_text_glyph(p, r, glyph, logical=logical)
        _draw_circle_outline(p, r)

    p.end()
    pix.setDevicePixelRatio(dpr)
    return pix


def message_status_icon(kind: str, *, logical: int = 32, dpr: float = 1.0) -> QIcon:
    return QIcon(message_status_pixmap(kind, logical=logical, dpr=dpr))
