# -*- coding: utf-8 -*-
"""预览区空态：虚线画布 + 中心图标 + 标题/副标题（去水印/媒体工坊等同款）。"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget


def theme_palette() -> dict:
    try:
        from app.app_state import AppState

        return dict(AppState.get().palette or {})
    except Exception:
        return {}


def paint_empty_preview_canvas(
    widget: QWidget,
    painter: QPainter,
    *,
    title: str,
    subtitle: str = "",
) -> None:
    """浅色虚线空态画布（禁止黑底灰字）。"""
    p = theme_palette()
    surface = QColor(str(p.get("surface") or "#F7F3EE"))
    raised = QColor(str(p.get("surface_raised") or p.get("panel") or "#EFE8E0"))
    border = QColor(str(p.get("border") or "#D4C4B0"))
    muted = QColor(str(p.get("text_secondary") or "#8A7A6A"))
    text = QColor(str(p.get("text_primary") or "#3D3229"))
    primary = QColor(str(p.get("primary") or "#C17F4E"))

    rect = widget.rect()
    painter.fillRect(rect, surface)
    tile = 14
    painter.setPen(Qt.PenStyle.NoPen)
    for y in range(0, rect.height(), tile):
        for x in range(0, rect.width(), tile):
            if ((x // tile) + (y // tile)) % 2 == 0:
                painter.fillRect(x, y, tile, tile, raised)

    inset = rect.adjusted(10, 10, -10, -10)
    pen = QPen(border)
    pen.setWidth(1)
    pen.setStyle(Qt.PenStyle.DashLine)
    pen.setDashPattern([5, 4])
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(QRectF(inset), 10, 10)

    cx, cy = rect.center().x(), rect.center().y() - 18
    painter.setBrush(QColor(primary.red(), primary.green(), primary.blue(), 28))
    painter.setPen(QPen(QColor(primary.red(), primary.green(), primary.blue(), 90), 1.5))
    painter.drawEllipse(QPoint(cx, cy), 28, 28)
    painter.setPen(QPen(primary, 2))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(cx - 12, cy - 9, 24, 18, 3, 3)
    painter.drawLine(cx - 6, cy + 2, cx - 1, cy - 4)
    painter.drawLine(cx - 1, cy - 4, cx + 5, cy + 3)
    painter.drawEllipse(QPoint(cx + 6, cy - 4), 2, 2)

    f1 = QFont(painter.font())
    f1.setBold(True)
    f1.setPointSize(max(10, f1.pointSize() + 1))
    painter.setFont(f1)
    painter.setPen(text)
    title_rect = QRect(rect.x() + 20, cy + 36, rect.width() - 40, 24)
    painter.drawText(
        title_rect,
        int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
        title,
    )

    if subtitle:
        f2 = QFont(painter.font())
        f2.setBold(False)
        f2.setPointSize(max(8, f2.pointSize() - 1))
        painter.setFont(f2)
        painter.setPen(muted)
        sub_rect = QRect(rect.x() + 24, cy + 58, rect.width() - 48, 40)
        painter.drawText(
            sub_rect,
            int(
                Qt.AlignmentFlag.AlignHCenter
                | Qt.AlignmentFlag.AlignTop
                | Qt.TextFlag.TextWordWrap
            ),
            subtitle,
        )
