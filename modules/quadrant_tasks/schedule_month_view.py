# -*- coding: utf-8 -*-
"""四象限日程月视图：通栏任务名 + 跨日色条；拖选日期新建；双击有任务日编辑。"""
from __future__ import annotations

from calendar import Calendar
from datetime import date, timedelta

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from modules.quadrant_tasks.task_store import (
    QUADRANT_KINDS,
    load_tasks,
    task_covers_day,
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
_DRAG_THRESHOLD_PX = 6


class ScheduleMonthView(QWidget):
    """月历网格：任务条通栏展示标题，支持 start→due 跨日。"""

    daySelected = Signal(date)
    dayCreateRequested = Signal(date)
    rangeCreateRequested = Signal(date, date)  # start, end（拖选）
    dayEditRequested = Signal(date)  # 双击有任务的日
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
        self._range_a: date | None = None
        self._range_b: date | None = None

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

    def clear_drag_range(self) -> None:
        self._range_a = None
        self._range_b = None
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

    def day_at(self, pos: QPoint) -> date | None:
        for rect, day in self._cell_hit:
            if rect.contains(pos):
                return day
        return None

    def task_at(self, pos: QPoint) -> str | None:
        for rect, tid in reversed(self._bar_hit):
            if rect.contains(pos):
                return tid
        return None

    def tasks_on_day(self, day: date) -> list[dict]:
        return [
            t
            for t in load_tasks()
            if not t.get("done") and task_covers_day(t, day)
        ]

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

        range_lo = range_hi = None
        if self._range_a is not None and self._range_b is not None:
            range_lo = min(self._range_a, self._range_b)
            range_hi = max(self._range_a, self._range_b)

        for wi, week in enumerate(weeks[:6]):
            for di, day in enumerate(week):
                cell = QRect(grid.left() + di * cw, grid.top() + wi * ch, cw, ch)
                self._cell_hit.append((cell, day))
                in_month = day.month == self._month
                if range_lo is not None and range_hi is not None and range_lo <= day <= range_hi:
                    painter.fillRect(
                        cell.adjusted(1, 1, -1, -1),
                        QColor(primary.red(), primary.green(), primary.blue(), 90),
                    )
                elif day == self._selected:
                    painter.fillRect(
                        cell.adjusted(1, 1, -1, -1),
                        QColor(primary.red(), primary.green(), primary.blue(), 55),
                    )
                painter.setPen(QPen(border, 1))
                painter.drawRect(cell)
                if range_lo is not None and range_hi is not None and range_lo <= day <= range_hi:
                    painter.setPen(QPen(primary, 2))
                    painter.drawRect(cell.adjusted(1, 1, -1, -1))
                painter.setPen(text if in_month else muted)
                if day.weekday() >= 5 and in_month:
                    painter.setPen(QColor("#EF9A9A"))
                painter.drawText(
                    cell.adjusted(4, 2, -4, 0),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                    str(day.day),
                )

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
            lanes: list[date] = []
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

    def hit_test_click(self, pos: QPoint, *, was_selected: date | None) -> None:
        """单击空白日：首次选中；再点同一空日 → 新建。有任务的日再点不新建（留给双击编辑）。点任务条 → 编辑。"""
        tid = self.task_at(pos)
        if tid:
            self.taskActivated.emit(tid)
            return
        day = self.day_at(pos)
        if day is None:
            return
        if was_selected is not None and day == was_selected:
            if self.tasks_on_day(day):
                self.set_selected(day)
            else:
                self.dayCreateRequested.emit(day)
        else:
            self.set_selected(day)


class _MonthCanvas(QWidget):
    def __init__(self, owner: ScheduleMonthView) -> None:
        super().__init__(owner)
        self._owner = owner
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._press_pos: QPoint | None = None
        self._press_day: date | None = None
        self._press_selected: date | None = None
        self._dragging = False
        self._press_on_bar = False

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._owner.paint_month(p, self.rect())

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        pos = event.position().toPoint()
        self._press_pos = pos
        self._press_selected = self._owner.selected_date()
        self._dragging = False
        tid = self._owner.task_at(pos)
        self._press_on_bar = bool(tid)
        if tid:
            # 任务条：按下即编辑（与原先一致）
            self._owner.taskActivated.emit(tid)
            self._press_day = None
            event.accept()
            return
        self._press_day = self._owner.day_at(pos)
        if self._press_day is not None:
            self._owner._range_a = self._press_day
            self._owner._range_b = self._press_day
            self.update()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if (
            self._press_day is not None
            and self._press_pos is not None
            and (event.buttons() & Qt.MouseButton.LeftButton)
            and not self._press_on_bar
        ):
            pos = event.position().toPoint()
            if (
                abs(pos.x() - self._press_pos.x()) >= _DRAG_THRESHOLD_PX
                or abs(pos.y() - self._press_pos.y()) >= _DRAG_THRESHOLD_PX
            ):
                self._dragging = True
            day = self._owner.day_at(pos)
            if day is not None:
                self._owner._range_b = day
                self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        press_day = self._press_day
        was_selected = self._press_selected
        dragging = self._dragging
        range_a = self._owner._range_a
        range_b = self._owner._range_b
        self._press_pos = None
        self._press_day = None
        self._press_selected = None
        self._dragging = False
        self._press_on_bar = False

        if press_day is None:
            self._owner.clear_drag_range()
            event.accept()
            return

        if dragging and range_a is not None and range_b is not None:
            a, b = min(range_a, range_b), max(range_a, range_b)
            self._owner.clear_drag_range()
            self._owner.set_selected(a)
            self._owner.rangeCreateRequested.emit(a, b)
            event.accept()
            return

        self._owner.clear_drag_range()
        self._owner.hit_test_click(event.position().toPoint(), was_selected=was_selected)
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseDoubleClickEvent(event)
            return
        pos = event.position().toPoint()
        if self._owner.task_at(pos):
            # 任务条双击：press 已打开编辑
            event.accept()
            return
        day = self._owner.day_at(pos)
        if day is None:
            event.accept()
            return
        if self._owner.tasks_on_day(day):
            self._owner.set_selected(day)
            self._owner.dayEditRequested.emit(day)
        event.accept()
