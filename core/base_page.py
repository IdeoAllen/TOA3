# -*- coding: utf-8 -*-
"""页面基类：主题刷新、状态上报、统一异常边界、焦点与 Tab 顺序。"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QLineEdit, QWidget

from core.error_handler import report_error, run_safe as _run_safe
from core.status_service import StatusLevel, report_status as _report_status
from core.ui_spec import apply_page_layout


class BasePage(QWidget):
    """所有业务模块页的基类。

    焦点约定（页面常规）：
    1. 覆写 ``primary_focus_widget`` 返回进页/操作后主输入控件。
    2. 覆写 ``focus_tab_widgets`` 列出 Tab 顺序（上→下、左→右）；``__init__`` 末尾调 ``apply_page_focus_policy()``。
    3. 壳层 ``on_enter`` 后会 ``schedule_primary_focus()``；子类在切换数据/新建/编辑后也可再调。
    4. 文本类主输入默认光标移到文末（``move_cursor_end=True``）。
    """

    page_id: str = ""
    page_title: str = ""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PageRoot")

    def primary_focus_widget(self) -> QWidget | None:
        """进页或数据切换后默认获焦的主输入；无则跳过。"""

        return None

    def focus_tab_widgets(self) -> list[QWidget]:
        """Tab 键顺序；子类按视觉顺序返回可聚焦控件。"""

        return []

    def apply_page_focus_policy(self) -> None:
        """按 ``focus_tab_widgets`` 串联 Tab 顺序（layout 完成后调用一次）。"""
        chain = [w for w in self.focus_tab_widgets() if w is not None]
        for i in range(len(chain) - 1):
            QWidget.setTabOrder(chain[i], chain[i + 1])

    def focus_primary(self, *, move_cursor_end: bool = True) -> None:
        """立即聚焦主输入控件。"""
        w = self.primary_focus_widget()
        if w is None or not w.isEnabled() or not w.isVisible():
            return
        w.setFocus(Qt.FocusReason.OtherFocusReason)
        if not move_cursor_end:
            return
        if hasattr(w, "textCursor"):
            cur = w.textCursor()
            cur.movePosition(QTextCursor.MoveOperation.End)
            w.setTextCursor(cur)
        elif isinstance(w, QLineEdit):
            w.setCursorPosition(len(w.text()))

    def schedule_primary_focus(self, *, move_cursor_end: bool = True) -> None:
        """延迟一帧聚焦（避免列表/切页抢焦点）。"""
        QTimer.singleShot(
            0,
            lambda: self.focus_primary(move_cursor_end=move_cursor_end),
        )

    def on_enter(self) -> None:
        """模块被切换到前台时调用。"""

    def on_leave(self) -> None:
        """模块被切走时调用。"""

    def on_theme_changed(self, theme_id: str, palette: dict) -> None:
        """全局换肤后调用（子类可刷新非 QSS 资源）。"""

    def report_status(self, text: str, *, level: StatusLevel = StatusLevel.INFO) -> None:
        _report_status(self, text, level=level, module_id=self.page_id or self.__class__.__name__)

    def apply_standard_page_layout(self) -> None:
        apply_page_layout(self)

    def handle_error(self, exc: BaseException, *, title: str | None = None) -> None:
        ctx = self.page_id or self.__class__.__name__
        report_error(self, exc, title=title, context=ctx)

    def run_safe(
        self,
        fn,
        *,
        title: str | None = None,
        success_status: str | None = None,
        on_success=None,
    ) -> bool:
        ctx = self.page_id or self.__class__.__name__
        result = _run_safe(
            fn,
            self,
            title=title,
            context=ctx,
            success_status=success_status,
            on_success=on_success,
        )
        return result is not None
