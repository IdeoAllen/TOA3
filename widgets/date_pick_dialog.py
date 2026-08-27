# -*- coding: utf-8 -*-
"""日期选择弹窗：主题月历 + 今天/确定（替代难用的 QDateEdit 系统弹层）。"""
from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout

from core.base_dialog import BaseDialog
from widgets.dialog_actions import DialogButtonRow
from widgets.displays import CalendarWidget
from widgets.themed_labels import HintLabel


class DatePickDialog(BaseDialog):
    """点选日期的终极方案：大月历、选中反显、一键今天。"""

    dialog_kind = "medium"

    def __init__(self, parent=None, *, initial: QDate | None = None, title: str = "选择日期") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self._apply_window_icon()
        day = initial if initial is not None and initial.isValid() else QDate.currentDate()

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(HintLabel("点选日期后确定；或点「今天」再确定。"))

        self._cal = CalendarWidget(self)
        self._cal.setSelectedDate(day)
        self._cal.setMinimumHeight(280)
        self._cal.activated.connect(self._on_activated)
        lay.addWidget(self._cal, 1)

        row = QHBoxLayout()
        from widgets import SecondaryButton

        btn_today = SecondaryButton("今天")
        btn_today.clicked.connect(self._goto_today)
        row.addWidget(btn_today)
        row.addStretch(1)
        buttons = DialogButtonRow()
        buttons.add_secondary("取消", self.reject)
        buttons.add_primary("确定", self.accept)
        row.addWidget(buttons)
        lay.addLayout(row)

        self._cal.highlight_selected()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self._apply_window_icon()

    def _apply_window_icon(self) -> None:
        try:
            from app.app_state import AppState
            from services.icon_registry import get_icon

            p = AppState.get().palette or {}
            color = str(p.get("primary") or "#2563EB")
            self.setWindowIcon(get_icon("calendar", color=color, size=24, parent=self))
        except Exception:
            pass

    def _goto_today(self) -> None:
        self._cal.setSelectedDate(QDate.currentDate())
        self._cal.highlight_selected()

    def _on_activated(self, qdate: QDate) -> None:
        # 双击日期格直接确认
        if qdate.isValid():
            self._cal.setSelectedDate(qdate)
            self.accept()

    def selected_qdate(self) -> QDate:
        return self._cal.selectedDate()
