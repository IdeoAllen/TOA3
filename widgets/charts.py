# -*- coding: utf-8 -*-
"""轻量图表控件（QPainter，跟主题 palette，禁止业务页 setStyleSheet）。"""
from __future__ import annotations

import math

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget


def _palette() -> dict:
    try:
        from app.app_state import AppState

        return AppState.get().palette or {}
    except Exception:
        return {}


# 高饱和、易区分的切片色（办公屏上更醒目）
_SLICE_FALLBACK = (
    "#E8793A",  # 铜橙（贴近 dms_copper）
    "#3B82F6",
    "#10B981",
    "#8B5CF6",
    "#F43F5E",
    "#06B6D4",
    "#F59E0B",
    "#EC4899",
    "#6366F1",
    "#14B8A6",
)


class PieChartWidget(QWidget):
    """文件类型占比环图：渐变扇区、悬停弹出、中心焦点、图例联动。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("PieChartWidget")
        self.setMinimumSize(260, 170)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self._slices: list[tuple[str, int]] = []
        self._empty_hint = "扫描后显示文件类型占比"
        self._hover_index: int = -1
        self._hover_t: float = 0.0  # 0→1 悬停动画
        self._pie_rect = QRectF()
        self._hole_rect = QRectF()
        self._hit: list[tuple[float, float, QRectF]] = []
        self._anim = QTimer(self)
        self._anim.setInterval(16)
        self._anim.timeout.connect(self._tick_anim)

    def set_slices(self, slices: list[tuple[str, int]] | None) -> None:
        items: list[tuple[str, int]] = []
        for label, count in slices or []:
            n = int(count or 0)
            if n > 0:
                items.append((str(label or "(无扩展名)"), n))
        items.sort(key=lambda kv: (-kv[1], kv[0].lower()))
        if len(items) > 8:
            head = items[:7]
            other = sum(n for _, n in items[7:])
            head.append(("其它", other))
            items = head
        self._slices = items
        self._hover_index = -1
        self._hover_t = 0.0
        self.setToolTip("")
        self.update()

    def set_empty_hint(self, text: str) -> None:
        self._empty_hint = str(text or "")
        self.update()

    def _colors(self) -> list[QColor]:
        p = _palette()
        primary = QColor(str(p.get("primary") or p.get("accent") or _SLICE_FALLBACK[0]))
        colors: list[QColor] = [primary]
        for hex_c in _SLICE_FALLBACK[1:]:
            c = QColor(hex_c)
            # 略向主色靠拢，整图更统一
            c = QColor(
                (c.red() * 3 + primary.red()) // 4,
                (c.green() * 3 + primary.green()) // 4,
                (c.blue() * 3 + primary.blue()) // 4,
            )
            colors.append(c)
        return colors

    def _total(self) -> int:
        return sum(n for _, n in self._slices)

    def _tick_anim(self) -> None:
        target = 1.0 if self._hover_index >= 0 else 0.0
        step = 0.18
        if abs(self._hover_t - target) < 0.02:
            self._hover_t = target
            if target <= 0:
                self._anim.stop()
            self.update()
            return
        self._hover_t += step if self._hover_t < target else -step
        self._hover_t = max(0.0, min(1.0, self._hover_t))
        self.update()

    def _hit_index(self, pos) -> int:
        if not self._slices or self._pie_rect.isEmpty():
            return -1
        pt = QPointF(pos)
        for i, (_s, _sp, leg) in enumerate(self._hit):
            if leg.contains(pt):
                return i
        c = self._pie_rect.center()
        dx = pt.x() - c.x()
        dy = pt.y() - c.y()
        dist = math.hypot(dx, dy)
        outer_r = min(self._pie_rect.width(), self._pie_rect.height()) / 2
        inner_r = (
            min(self._hole_rect.width(), self._hole_rect.height()) / 2
            if not self._hole_rect.isEmpty()
            else outer_r * 0.55
        )
        # 悬停时外圈略放大，命中区放宽
        if dist > outer_r + 8 or dist < inner_r * 0.75:
            return -1
        ang = QLineF(c, pt).angle()
        for i, (start, span_cw, _leg) in enumerate(self._hit):
            delta = (start - ang) % 360.0
            if 0 <= delta <= span_cw + 0.05:
                return i
        return -1

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        pos = event.position() if hasattr(event, "position") else event.pos()
        idx = self._hit_index(pos)
        if idx != self._hover_index:
            self._hover_index = idx
            if 0 <= idx < len(self._slices):
                label, count = self._slices[idx]
                total = self._total() or 1
                pct = 100.0 * count / total
                tip = f"{label}  ·  {count} 个  ·  {pct:.1f}%"
                self.setToolTip(tip)
                gp = (
                    event.globalPosition().toPoint()
                    if hasattr(event, "globalPosition")
                    else event.globalPos()
                )
                QToolTip.showText(gp, tip, self)
            else:
                self.setToolTip("")
                QToolTip.hideText()
            if not self._anim.isActive():
                self._anim.start()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._hover_index >= 0 or self._hover_t > 0:
            self._hover_index = -1
            self.setToolTip("")
            QToolTip.hideText()
            if not self._anim.isActive():
                self._anim.start()
        super().leaveEvent(event)

    def _draw_soft_shadow(self, painter: QPainter, pie: QRectF) -> None:
        c = pie.center()
        r = min(pie.width(), pie.height()) / 2
        for i, alpha in enumerate((28, 18, 10)):
            grow = 6 + i * 5
            shadow = QRectF(c.x() - r - grow, c.y() - r - grow + 3, (r + grow) * 2, (r + grow) * 2)
            grad = QRadialGradient(c, r + grow)
            grad.setColorAt(0.55, QColor(0, 0, 0, 0))
            grad.setColorAt(0.82, QColor(0, 0, 0, alpha // 2))
            grad.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(grad)
            painter.drawEllipse(shadow)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p = _palette()
        text_c = QColor(str(p.get("text_primary") or "#1E293B"))
        muted = QColor(str(p.get("text_secondary") or "#64748B"))
        surface = QColor(str(p.get("surface") or p.get("panel") or "#FFFFFF"))
        primary = QColor(str(p.get("primary") or "#E8793A"))

        rect = self.rect().adjusted(4, 4, -4, -4)
        self._hit = []
        self._pie_rect = QRectF()
        self._hole_rect = QRectF()
        if rect.width() < 40 or rect.height() < 40:
            return

        total = self._total()
        if total <= 0:
            # 空态：淡环引导
            side = min(rect.width() * 0.55, rect.height() - 8)
            empty = QRectF(
                rect.center().x() - side / 2,
                rect.center().y() - side / 2,
                side,
                side,
            )
            painter.setPen(QPen(QColor(muted.red(), muted.green(), muted.blue(), 80), 10))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(empty.adjusted(12, 12, -12, -12))
            painter.setPen(muted)
            font = painter.font()
            font.setPointSize(max(9, font.pointSize()))
            painter.setFont(font)
            painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), self._empty_hint)
            return

        # 图例列宽按字宽测算，避免名/% 叠字
        name_font = QFont(painter.font())
        name_font.setPointSize(max(9, name_font.pointSize()))
        pct_font = QFont(painter.font())
        pct_font.setBold(True)
        pct_font.setPointSize(max(10, pct_font.pointSize()))
        painter.setFont(name_font)
        name_fm = painter.fontMetrics()
        painter.setFont(pct_font)
        pct_fm = painter.fontMetrics()
        max_name_w = max(
            (name_fm.horizontalAdvance(lab if len(lab) <= 10 else lab[:9] + "…") for lab, _ in self._slices),
            default=48,
        )
        pct_col_w = max(pct_fm.horizontalAdvance("100%"), pct_fm.horizontalAdvance("88%")) + 4
        swatch_w = 14
        gap_name_pct = 10
        legend_pad = 6
        legend_w = int(
            min(
                max(118, swatch_w + 8 + max_name_w + gap_name_pct + pct_col_w + legend_pad),
                max(118, int(rect.width() * 0.42)),
            )
        )
        pie_budget = rect.width() - legend_w - 16
        pie_side = min(rect.height() - 8, pie_budget)
        pie_side = max(120, pie_side)
        pie_rect = QRectF(
            rect.x() + max(2, (pie_budget - pie_side) / 2),
            rect.y() + (rect.height() - pie_side) / 2,
            pie_side,
            pie_side,
        ).adjusted(6, 6, -6, -6)
        self._pie_rect = QRectF(pie_rect)
        self._draw_soft_shadow(painter, pie_rect)

        colors = self._colors()
        hole_ratio = 0.52
        start_deg = 90.0
        gap_deg = 1.6 if len(self._slices) > 1 else 0.0
        # 右侧留给图例，环上标签不得侵入
        legend_zone = QRectF(rect.right() - legend_w - 4, rect.y(), legend_w + 8, rect.height())
        slice_meta: list[tuple[float, float, float, float]] = []  # start, span_cw, mid_ang, pct

        for i, (label, count) in enumerate(self._slices):
            raw_span = 360.0 * (count / total)
            span_cw = max(0.5, raw_span - gap_deg)
            color = QColor(colors[i % len(colors)])
            is_hover = i == self._hover_index
            pop = (8.0 * self._hover_t) if is_hover else 0.0
            mid_ang = math.radians(start_deg - span_cw / 2)
            ox = math.cos(mid_ang) * pop
            oy = -math.sin(mid_ang) * pop
            draw_rect = pie_rect.translated(ox, oy)
            if is_hover:
                grow = 2.5 * self._hover_t
                draw_rect = draw_rect.adjusted(-grow, -grow, grow, grow)

            c = draw_rect.center()
            rg = QRadialGradient(c, min(draw_rect.width(), draw_rect.height()) / 2)
            light = color.lighter(128)
            dark = color.darker(115)
            if is_hover:
                light = color.lighter(140)
                dark = color
            rg.setColorAt(0.0, light)
            rg.setColorAt(0.55, color)
            rg.setColorAt(1.0, dark)

            painter.setBrush(rg)
            if is_hover:
                painter.setPen(QPen(QColor(255, 255, 255, 200), 2.0))
            else:
                painter.setPen(QPen(QColor(255, 255, 255, 90), 1.0))
            painter.drawPie(draw_rect, int(start_deg * 16), int(-span_cw * 16))

            pct = 100.0 * count / total
            slice_meta.append((start_deg, span_cw + gap_deg, mid_ang, pct))
            self._hit.append((start_deg, span_cw + gap_deg, QRectF()))
            start_deg = (start_deg - raw_span) % 360.0

        # 环带百分比：仅大扇区，且标签矩形不进图例区
        for i, (_label, count) in enumerate(self._slices):
            _start, _span, mid_ang, pct = slice_meta[i]
            if pct < 8.0:
                continue
            is_hover = i == self._hover_index
            pop = (8.0 * self._hover_t) if is_hover else 0.0
            ox = math.cos(mid_ang) * pop
            oy = -math.sin(mid_ang) * pop
            draw_rect = pie_rect.translated(ox, oy)
            c = draw_rect.center()
            r_mid = min(draw_rect.width(), draw_rect.height()) / 2 * ((1 + hole_ratio) / 2)
            lx = c.x() + math.cos(mid_ang) * r_mid
            ly = c.y() - math.sin(mid_ang) * r_mid
            tag = f"{pct:.0f}%"
            f = QFont(painter.font())
            f.setBold(True)
            f.setPointSize(max(10, f.pointSize() + 1))
            painter.setFont(f)
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(tag) + 12
            th = fm.height() + 6
            br = QRectF(lx - tw / 2, ly - th / 2, tw, th)
            if br.intersects(legend_zone) or not pie_rect.contains(br.center()):
                continue
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(20, 20, 24, 200 if is_hover else 170))
            painter.drawRoundedRect(br, 7, 7)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(br, int(Qt.AlignmentFlag.AlignCenter), tag)

        # 中心盘 + 内阴影环
        hole = pie_rect.adjusted(
            pie_rect.width() * (1 - hole_ratio) / 2,
            pie_rect.height() * (1 - hole_ratio) / 2,
            -pie_rect.width() * (1 - hole_ratio) / 2,
            -pie_rect.height() * (1 - hole_ratio) / 2,
        )
        self._hole_rect = QRectF(hole)

        ring = QRadialGradient(hole.center(), min(hole.width(), hole.height()) / 2)
        ring.setColorAt(0.0, surface)
        ring.setColorAt(0.85, surface)
        ring.setColorAt(1.0, QColor(0, 0, 0, 18))
        painter.setBrush(ring)
        painter.setPen(QPen(QColor(primary.red(), primary.green(), primary.blue(), 40), 1.5))
        painter.drawEllipse(hole)

        if 0 <= self._hover_index < len(self._slices) and self._hover_t > 0.15:
            lab, cnt = self._slices[self._hover_index]
            pct = 100.0 * cnt / total
            title = lab
            sub = f"{pct:.1f}% · {cnt}"
        else:
            title = str(total)
            sub = "个文件"

        painter.setPen(text_c)
        f1 = QFont(painter.font())
        f1.setBold(True)
        f1.setPointSize(max(14, f1.pointSize() + 4))
        painter.setFont(f1)
        title_rect = QRectF(hole.x(), hole.y() + hole.height() * 0.22, hole.width(), hole.height() * 0.38)
        elide = title if len(title) <= 10 else title[:9] + "…"
        painter.drawText(title_rect, int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom), elide)

        painter.setPen(muted)
        f2 = QFont(painter.font())
        f2.setBold(False)
        f2.setPointSize(max(8, f2.pointSize() - 5))
        painter.setFont(f2)
        sub_rect = QRectF(hole.x(), hole.y() + hole.height() * 0.55, hole.width(), hole.height() * 0.28)
        painter.drawText(sub_rect, int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop), sub)

        # 图例：色块 | 名称(elide) | 右对齐%
        legend_x = rect.right() - legend_w
        n = len(self._slices)
        row_h = max(22, min(28, int((rect.height() - 8) / max(1, n))))
        legend_y = rect.y() + max(0, (rect.height() - n * row_h) / 2)
        for i, (label, count) in enumerate(self._slices):
            y = legend_y + i * row_h
            leg = QRectF(legend_x, y, legend_w - 2, row_h - 1)
            start, span, _ = self._hit[i]
            self._hit[i] = (start, span, leg)
            is_hover = i == self._hover_index
            color = QColor(colors[i % len(colors)])

            if is_hover and self._hover_t > 0.2:
                bg = QColor(primary.red(), primary.green(), primary.blue(), int(28 * self._hover_t))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(bg)
                painter.drawRoundedRect(leg.adjusted(-2, 0, 0, 0), 4, 4)

            sw = 10 + (2 if is_hover else 0)
            painter.setBrush(color)
            painter.setPen(QPen(QColor(255, 255, 255, 160), 1.0))
            painter.drawRoundedRect(
                QRectF(legend_x + 2, y + (row_h - sw) / 2, sw, sw),
                3,
                3,
            )

            pct = 100.0 * count / total
            pct_text = f"{pct:.0f}%"
            pct_rect = QRectF(
                legend_x + legend_w - legend_pad - pct_col_w,
                y,
                pct_col_w,
                row_h - 1,
            )
            name_rect = QRectF(
                legend_x + swatch_w + 6,
                y,
                max(24.0, pct_rect.left() - gap_name_pct - (legend_x + swatch_w + 6)),
                row_h - 1,
            )

            painter.setFont(name_font)
            painter.setPen(primary if is_hover else text_c)
            shown = name_fm.elidedText(
                label,
                Qt.TextElideMode.ElideRight,
                int(name_rect.width()),
            )
            painter.drawText(
                name_rect,
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                shown,
            )

            painter.setFont(pct_font)
            painter.setPen(primary if is_hover else muted)
            painter.drawText(
                pct_rect,
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
                pct_text,
            )
