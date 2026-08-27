# -*- coding: utf-8 -*-
"""四象限日程月视图：通栏任务名 + 跨日色条（对标排期块）。"""
from __future__ import annotations

from calendar import Calendar
from datetime import date, timedelta

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from modules.quadrant_tasks.task_store import (
    QUADRANT_KINDS,
    load_tasks,
    task_span,
)
from widgets import HintLabel, InlineButton, SecondaryButton

_KIND_COLORS = {
    "danger": QColor("#E57373"),
    "warning": QColor("#FFB74D"),
    "success": QColor("#7CB342"),
    "info": QColor("#64B5F6"),
}

_WEEKDAYS = ("一", "二", "三", "四", "五", "六", "日")


class ScheduleMonthView(QWidget):
    """月历网格：任务条通栏展示标题，支持 start→due 跨日。"""

    daySelected = Signal(date)
    dayCreateRequested = Signal(date)
    taskActivated = Signal(str)
    monthChanged = Signal(int, int)  # year, month

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ScheduleMonthView")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(360)
        self.setMouseTracking(True)

        today = date.today()
        self._year = today.year
        self._month = today.month
        self._selected = today
        self._hover_task: str | None = None
        self._bar_hit: list[tuple[QRect, str]] = []
        self._cell_hit: list[tuple[QRect, date]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        nav = QHBoxLayout()
        self._btn_prev = InlineButton("‹")
        self._btn_prev.setToolTip("上一月")
        self._btn_prev.clicked.connect(self._prev_month)
        nav.addWidget(self._btn_prev)
        self._title = HintLabel("")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav.addWidget(self._title, 1)
        self._btn_next = InlineButton("›")
        self._btn_next.setToolTip("下一月")
        self._btn_next.clicked.connect(self._next_month)
        nav.addWidget(self._btn_next)
        btn_today = SecondaryButton("今天")
        btn_today.clicked.connect(self._goto_today)
        nav.addWidget(btn_today)
        root.addLayout(nav)

        self._canvas = _MonthCanvas(self)
        root.addWidget(self._canvas, 1)
        self._refresh_title()

    def selected_date(self) -> date:
        return self._selected

    def set_selected(self, day: date) -> None:
        self._selected = day
        if day.year != self._year or day.month != self._month:
            self._year = day.year
            self._month = day.month
            self._refresh_title()
            self.monthChanged.emit(self._year, self._month)
        self._canvas.update()
        self.daySelected.emit(day)

    def set_month(self, year: int, month: int) -> None:
        self._year = year
        self._month = month
        self._refresh_title()
        self._canvas.update()
        self.monthChanged.emit(year, month)

    def refresh_tasks(self) -> None:
        self._canvas.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(520, 420)

    def _refresh_title(self) -> None:
        self._title.setText(f"{self._year}年{self._month:02d}月")

    def _prev_month(self) -> None:
        if self._month == 1:
            self.set_month(self._year - 1, 12)
        else:
            self.set_month(self._year, self._month - 1)

    def _next_month(self) -> None:
        if self._month == 12:
            self.set_month(self._year + 1, 1)
        else:
            self.set_month(self._year, self._month + 1)

    def _goto_today(self) -> None:
        self.set_selected(date.today())

    def paint_month(self, painter: QPainter, rect: QRect) -> None:
        self._bar_hit.clear()
        self._cell_hit.clear()
        try:
            from app.app_state import AppState

            pal = AppState.get().palette or {}
        except Exception:
            pal = {}
        surface = QColor(str(pal.get("surface") or "#33261E"))
        text = QColor(str(pal.get("text_primary") or "#F0E6DC"))
        muted = QColor(str(pal.get("text_secondary") or "#B8A99A"))
        border = QColor(str(pal.get("border") or "#4A3728"))
        primary = QColor(str(pal.get("primary") or "#C17F4E"))

        painter.fillRect(rect, surface)
        header_h = 28
        grid = QRect(rect.left(), rect.top() + header_h, rect.width(), rect.height() - header_h)
        cols, rows = 7, 6
        cw = max(1, grid.width() // cols)
        ch = max(1, grid.height() // rows)

        font = QFont(painter.font())
        font.setPointSize(max(9, font.pointSize()))
        painter.setFont(font)
        for i, name in enumerate(_WEEKDAYS):
            r = QRect(grid.left() + i * cw, rect.top(), cw, header_h)
            painter.setPen(QColor("#E57373") if i >= 5 else muted)
            painter.drawText(r, Qt.AlignmentFlag.AlignCenter, name)

        cal = Calendar(firstweekday=0)  # Monday
        weeks = cal.monthdatescalendar(self._year, self._month)
        while len(weeks) < 6:
            last = weeks[-1][-1]
            weeks.append([last + timedelta(days=i) for i in range(1, 8)])

        # cells
        for wi, week in enumerate(weeks[:6]):
            for di, day in enumerate(week):
                cell = QRect(grid.left() + di * cw, grid.top() + wi * ch, cw, ch)
                self._cell_hit.append((cell, day))
                in_month = day.month == self._month
                if day == self._selected:
                    painter.fillRect(cell.adjusted(1, 1, -1, -1), QColor(primary.red(), primary.green(), primary.blue(), 55))
                painter.setPen(QPen(border, 1))
                painter.drawRect(cell)
                painter.setPen(text if in_month else muted)
                if day.weekday() >= 5 and in_month:
                    painter.setPen(QColor("#EF9A9A"))
                painter.drawText(
                    cell.adjusted(4, 2, -4, 0),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                    str(day.day),
                )

        # task bars per week
        tasks = [t for t in load_tasks() if not t.get("done")]
        bar_h = 16
        gap = 2
        top_pad = 20
        for wi, week in enumerate(weeks[:6]):
            week_start, week_end = week[0], week[6]
            spans: list[tuple[date, date, dict]] = []
            for t in tasks:
                span = task_span(t)
                if span is None:
                    continue
                a, b = span
                if b < week_start or a > week_end:
                    continue
                spans.append((max(a, week_start), min(b, week_end), t))
            spans.sort(key=lambda x: (x[0], x[1], str(x[2].get("title") or "")))
            lanes: list[date] = []  # lane end dates
            for a, b, t in spans:
                lane = 0
                while lane < len(lanes) and lanes[lane] >= a:
                    lane += 1
                if lane == len(lanes):
                    lanes.append(b)
                else:
                    lanes[lane] = b
                c0 = (a - week_start).days
                c1 = (b - week_start).days
                x = grid.left() + c0 * cw + 3
                y = grid.top() + wi * ch + top_pad + lane * (bar_h + gap)
                w = (c1 - c0 + 1) * cw - 6
                if y + bar_h > grid.top() + (wi + 1) * ch - 2:
                    continue
                kind = QUADRANT_KINDS.get(str(t.get("quadrant") or ""), "info")
                color = _KIND_COLORS.get(kind, _KIND_COLORS["info"])
                bar = QRect(x, y, max(24, w), bar_h)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                painter.drawRoundedRect(bar, 3, 3)
                painter.setPen(QColor("#1A120E"))
                title = str(t.get("title") or "")
                painter.drawText(
                    bar.adjusted(4, 0, -4, 0),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    title,
                )
                tid = str(t.get("id") or "")
                if tid:
                    self._bar_hit.append((bar, tid))

    def hit_test(self, pos: QPoint) -> None:
        """单击空白日：首次选中；再点同一日 → 新建。点任务条 → 编辑。"""
        for rect, tid in reversed(self._bar_hit):
            if rect.contains(pos):
                self.taskActivated.emit(tid)
                return
        for rect, day in self._cell_hit:
            if rect.contains(pos):
                if day == self._selected:
                    self.dayCreateRequested.emit(day)
                else:
                    self.set_selected(day)
                return


class _MonthCanvas(QWidget):
    def __init__(self, owner: ScheduleMonthView) -> None:
        super().__init__(owner)
        self._owner = owner
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._owner.paint_month(p, self.rect())

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._owner.hit_test(event.position().toPoint())
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        # 双击空白日：第二次 press 已触发新建，此处避免再开一次
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
