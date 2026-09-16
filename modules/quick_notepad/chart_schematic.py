# -*- coding: utf-8 -*-
"""组件库图表卡：迷你样子（QPainter），不启 WebEngine。"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

from app.app_state import AppState


def _pal_color(key: str, fallback: str) -> QColor:
    pal = AppState.get().palette or {}
    raw = str(pal.get(key) or "").strip()
    c = QColor(raw) if raw else QColor(fallback)
    return c if c.isValid() else QColor(fallback)


class ChartSchematic(QWidget):
    """卡片内缩略：一眼看出拖入后是哪种图。"""

    def __init__(self, block_id: str, parent=None) -> None:
        super().__init__(parent)
        self._bid = str(block_id or "").strip()
        self.setObjectName("NotepadComponentChartSchematic")
        self.setFixedHeight(72)
        self.setMinimumWidth(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        border = _pal_color("border", "#cbd5e1")
        text = _pal_color("text", "#1f2937")
        text2 = _pal_color("text2", "#64748b")
        primary = _pal_color("primary", "#2563eb")
        surface = _pal_color("surface", "#ffffff")
        accent = _pal_color("accent", primary.name())
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        p.fillRect(r, surface)
        p.setPen(QPen(border, 1.0))
        p.drawRoundedRect(r, 6, 6)
        inner = r.adjusted(6, 6, -6, -6)
        bid = self._bid
        if bid == "mermaid_flow":
            self._paint_flow_td(p, inner, primary, text, text2)
        elif bid == "mermaid_lr":
            self._paint_flow_lr(p, inner, primary, text, text2)
        elif bid == "mermaid_seq":
            self._paint_seq(p, inner, primary, text, text2)
        elif bid == "mermaid_pie":
            self._paint_pie(p, inner, primary, accent, text2)
        elif bid == "mermaid_gantt":
            self._paint_gantt(p, inner, primary, accent, text2)
        else:
            p.setPen(text2)
            p.drawText(inner, int(Qt.AlignmentFlag.AlignCenter), "图表")
        p.end()

    def _box(
        self,
        p: QPainter,
        rect: QRectF,
        label: str,
        fill: QColor,
        pen: QColor,
        text: QColor,
    ) -> None:
        p.setPen(QPen(pen, 1.2))
        p.setBrush(fill)
        p.drawRoundedRect(rect, 4, 4)
        font = QFont(p.font())
        font.setPointSize(max(7, font.pointSize() - 2))
        p.setFont(font)
        p.setPen(text)
        p.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), label)

    def _arrow_down(self, p: QPainter, x: float, y0: float, y1: float, color: QColor) -> None:
        p.setPen(QPen(color, 1.4))
        p.drawLine(QPointF(x, y0), QPointF(x, y1 - 4))
        tip = QPolygonF(
            [QPointF(x, y1), QPointF(x - 3.5, y1 - 5), QPointF(x + 3.5, y1 - 5)]
        )
        p.setBrush(color)
        p.drawPolygon(tip)

    def _arrow_right(self, p: QPainter, x0: float, x1: float, y: float, color: QColor) -> None:
        p.setPen(QPen(color, 1.4))
        p.drawLine(QPointF(x0, y), QPointF(x1 - 4, y))
        tip = QPolygonF(
            [QPointF(x1, y), QPointF(x1 - 5, y - 3.5), QPointF(x1 - 5, y + 3.5)]
        )
        p.setBrush(color)
        p.drawPolygon(tip)

    def _paint_flow_td(
        self, p: QPainter, r: QRectF, primary: QColor, text: QColor, text2: QColor
    ) -> None:
        fill = QColor(primary)
        fill.setAlpha(28)
        w = min(72.0, r.width() * 0.55)
        h = 14.0
        cx = r.center().x()
        y1 = r.top()
        y2 = r.center().y() - h / 2
        y3 = r.bottom() - h
        self._box(p, QRectF(cx - w / 2, y1, w, h), "开始", fill, primary, text)
        self._arrow_down(p, cx, y1 + h + 1, y2 - 1, text2)
        self._box(p, QRectF(cx - w / 2, y2, w, h), "处理", fill, primary, text)
        self._arrow_down(p, cx, y2 + h + 1, y3 - 1, text2)
        self._box(p, QRectF(cx - w / 2, y3, w, h), "结束", fill, primary, text)

    def _paint_flow_lr(
        self, p: QPainter, r: QRectF, primary: QColor, text: QColor, text2: QColor
    ) -> None:
        fill = QColor(primary)
        fill.setAlpha(28)
        box_w = max(28.0, (r.width() - 28) / 3)
        h = 18.0
        y = r.center().y() - h / 2
        labels = ("输入", "加工", "输出")
        xs = [r.left(), r.left() + box_w + 10, r.left() + 2 * (box_w + 10)]
        for i, lab in enumerate(labels):
            self._box(p, QRectF(xs[i], y, box_w, h), lab, fill, primary, text)
            if i < 2:
                self._arrow_right(p, xs[i] + box_w + 1, xs[i + 1] - 1, r.center().y(), text2)

    def _paint_seq(
        self, p: QPainter, r: QRectF, primary: QColor, text: QColor, text2: QColor
    ) -> None:
        fill = QColor(primary)
        fill.setAlpha(28)
        left_x = r.left() + 18
        right_x = r.right() - 18
        top = r.top() + 2
        bot = r.bottom() - 2
        # 参与者
        self._box(p, QRectF(left_x - 16, top, 32, 12), "用户", fill, primary, text)
        self._box(p, QRectF(right_x - 16, top, 32, 12), "系统", fill, primary, text)
        pen = QPen(text2, 1.0, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawLine(QPointF(left_x, top + 14), QPointF(left_x, bot))
        p.drawLine(QPointF(right_x, top + 14), QPointF(right_x, bot))
        # 请求 / 响应
        y1 = top + 28
        y2 = top + 46
        self._arrow_right(p, left_x + 2, right_x - 2, y1, primary)
        p.setPen(text2)
        font = QFont(p.font())
        font.setPointSize(max(6, font.pointSize() - 3))
        p.setFont(font)
        p.drawText(QRectF(left_x + 4, y1 - 12, right_x - left_x - 8, 10),
                   int(Qt.AlignmentFlag.AlignCenter), "请求")
        # 反向箭头
        p.setPen(QPen(primary, 1.4))
        p.drawLine(QPointF(right_x - 2, y2), QPointF(left_x + 4, y2))
        tip = QPolygonF(
            [
                QPointF(left_x + 2, y2),
                QPointF(left_x + 7, y2 - 3.5),
                QPointF(left_x + 7, y2 + 3.5),
            ]
        )
        p.setBrush(primary)
        p.drawPolygon(tip)
        p.setPen(text2)
        p.drawText(QRectF(left_x + 4, y2 - 12, right_x - left_x - 8, 10),
                   int(Qt.AlignmentFlag.AlignCenter), "响应")

    def _paint_pie(
        self, p: QPainter, r: QRectF, primary: QColor, accent: QColor, text2: QColor
    ) -> None:
        side = min(r.width(), r.height()) - 4
        pie = QRectF(r.center().x() - side / 2, r.center().y() - side / 2, side, side)
        c1 = QColor(primary)
        c2 = QColor(accent)
        c3 = QColor(text2)
        c3.setAlpha(160)
        # Qt angles: 16ths of degree, 0=3 o'clock, counter-clockwise
        spans = ((0, 160 * 16, c1), (160 * 16, 110 * 16, c2), (270 * 16, 90 * 16, c3))
        for start, span, col in spans:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col)
            p.drawPie(pie, start, span)
        p.setPen(QPen(_pal_color("border", "#cbd5e1"), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(pie)

    def _paint_gantt(
        self, p: QPainter, r: QRectF, primary: QColor, accent: QColor, text2: QColor
    ) -> None:
        rows = (
            ("筹备", 0.05, 0.35, primary),
            ("执行", 0.30, 0.70, accent),
            ("收尾", 0.65, 0.92, text2),
        )
        row_h = 12.0
        gap = 4.0
        total_h = 3 * row_h + 2 * gap
        y0 = r.center().y() - total_h / 2
        label_w = 28.0
        bar_left = r.left() + label_w + 4
        bar_w = r.width() - label_w - 6
        font = QFont(p.font())
        font.setPointSize(max(6, font.pointSize() - 3))
        p.setFont(font)
        for i, (lab, a, b, col) in enumerate(rows):
            y = y0 + i * (row_h + gap)
            p.setPen(text2)
            p.drawText(
                QRectF(r.left(), y, label_w, row_h),
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                lab,
            )
            fill = QColor(col)
            fill.setAlpha(200)
            br = QRectF(bar_left + a * bar_w, y + 1, max(8.0, (b - a) * bar_w), row_h - 2)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fill)
            p.drawRoundedRect(br, 3, 3)


class ImageSchematic(QWidget):
    """图片/图标组件卡：框出插图样子，并标默认大小。"""

    def __init__(self, parent=None, *, kind: str = "image") -> None:
        super().__init__(parent)
        self._kind = "icon" if str(kind).strip().lower() == "icon" else "image"
        self.setObjectName("NotepadComponentImageSchematic")
        self.setFixedHeight(56)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        border = _pal_color("border", "#cbd5e1")
        text2 = _pal_color("text2", "#64748b")
        primary = _pal_color("primary", "#2563eb")
        surface = _pal_color("surface_alt", "#f8fafc")
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        p.fillRect(r, surface)
        p.setPen(QPen(border, 1.2, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, 6, 6)
        mid = r.center()
        if self._kind == "icon":
            # 小方标示意
            box = QRectF(mid.x() - 12, mid.y() - 16, 24, 24)
            fill = QColor(primary)
            fill.setAlpha(70)
            p.setPen(QPen(primary, 1.2))
            p.setBrush(fill)
            p.drawRoundedRect(box, 5, 5)
            p.setPen(text2)
            font = QFont(p.font())
            font.setPointSize(max(7, font.pointSize() - 2))
            p.setFont(font)
            p.drawText(
                QRectF(r.left(), r.bottom() - 16, r.width(), 14),
                int(Qt.AlignmentFlag.AlignCenter),
                "默认 48px · 可改",
            )
        else:
            path = QPainterPath()
            path.moveTo(mid.x() - 22, mid.y() + 8)
            path.lineTo(mid.x() - 8, mid.y() - 8)
            path.lineTo(mid.x() + 2, mid.y())
            path.lineTo(mid.x() + 12, mid.y() - 12)
            path.lineTo(mid.x() + 22, mid.y() + 8)
            path.closeSubpath()
            fill = QColor(primary)
            fill.setAlpha(60)
            p.fillPath(path, fill)
            p.setPen(QPen(primary, 1.2))
            p.drawPath(path)
            sun = QRectF(mid.x() + 10, mid.y() - 16, 10, 10)
            p.setBrush(QColor(primary))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(sun)
            p.setPen(text2)
            font = QFont(p.font())
            font.setPointSize(max(7, font.pointSize() - 2))
            p.setFont(font)
            p.drawText(
                QRectF(r.left(), r.bottom() - 16, r.width(), 14),
                int(Qt.AlignmentFlag.AlignCenter),
                "默认中图 360 · 可改",
            )
        p.end()
