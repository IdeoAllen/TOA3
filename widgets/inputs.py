# -*- coding: utf-8 -*-
"""标准输入控件。"""
from __future__ import annotations

from PySide6.QtCore import QDate, QEvent, QSize, Qt, Signal
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from widgets.metrics import BUTTON_MIN_HEIGHT


class LineEdit(QLineEdit):
    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setMinimumHeight(BUTTON_MIN_HEIGHT)


class PasswordLineEdit(LineEdit):
    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setEchoMode(QLineEdit.EchoMode.Password)


class PlainTextEdit(QPlainTextEdit):
    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(parent)
        if text:
            self.setPlainText(text)
        self.setMinimumHeight(120)


class ReadOnlyPlainTextEdit(PlainTextEdit):
    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setReadOnly(True)


class TextEdit(QTextEdit):
    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(parent)
        if text:
            self.setPlainText(text)
        self.setMinimumHeight(120)


class ReadOnlyTextEdit(TextEdit):
    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setReadOnly(True)


class ComboBox(QComboBox):
    """整框可点展开；未聚焦时滚轮不误改选项。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(BUTTON_MIN_HEIGHT)
        self.setMaxVisibleItems(14)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)

    def showPopup(self) -> None:  # noqa: N802
        self.view().setMinimumWidth(max(self.width(), 160))
        super().showPopup()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.showPopup()
            event.accept()
            return
        super().mousePressEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


class SpinBox(QWidget):
    """一体式数字框：数值后紧跟上下箭头（不贴控件右缘）。"""

    valueChanged = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ThemedSpinBox")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumHeight(BUTTON_MIN_HEIGHT)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.setProperty("focusRing", "false")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 4, 0)
        lay.setSpacing(2)

        self._box = QSpinBox()
        self._box.setObjectName("ThemedSpinBoxField")
        self._box.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._box.setFrame(False)
        self._box.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._box.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._box.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._box.valueChanged.connect(self.valueChanged.emit)
        self._box.valueChanged.connect(self._sync_field_width)
        self._box.textChanged.connect(self._sync_field_width)
        # PySide6 部分版本无 QSpinBox.rangeChanged，改由 setRange/setMinimum/setMaximum 触发
        self._box.installEventFilter(self)
        lay.addWidget(self._box, 0)

        btn_col = QWidget()
        btn_col.setObjectName("SpinBoxButtons")
        btn_lay = QVBoxLayout(btn_col)
        btn_lay.setContentsMargins(0, 3, 0, 3)
        btn_lay.setSpacing(0)

        self._btn_up = QToolButton()
        self._btn_up.setObjectName("SpinBoxUpButton")
        self._btn_up.setAutoRaise(True)
        self._btn_up.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_up.setFixedSize(22, 12)
        self._btn_up.clicked.connect(self._box.stepUp)

        self._btn_down = QToolButton()
        self._btn_down.setObjectName("SpinBoxDownButton")
        self._btn_down.setAutoRaise(True)
        self._btn_down.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_down.setFixedSize(22, 12)
        self._btn_down.clicked.connect(self._box.stepDown)

        btn_lay.addWidget(self._btn_up)
        btn_lay.addWidget(self._btn_down)
        lay.addWidget(btn_col, 0)

        self._sync_field_width()
        self._refresh_icons()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self._box and event.type() in (
            QEvent.Type.FocusIn,
            QEvent.Type.FocusOut,
        ):
            self.setProperty("focusRing", "true" if self._box.hasFocus() else "false")
            sty = self.style()
            sty.unpolish(self)
            sty.polish(self)
        return super().eventFilter(obj, event)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._refresh_icons()

    def _refresh_icons(self) -> None:
        try:
            from app.app_state import AppState
            from services.icon_registry import chevron_icon

            fg = str((AppState.get().palette or {}).get("text_secondary") or "#6B7C94")
            self._btn_up.setIcon(chevron_icon("up", color=fg, size=10, parent=self))
            self._btn_down.setIcon(chevron_icon("down", color=fg, size=10, parent=self))
            self._btn_up.setIconSize(QSize(10, 10))
            self._btn_down.setIconSize(QSize(10, 10))
        except Exception:
            self._btn_up.setText("▴")
            self._btn_down.setText("▾")

    def _sync_field_width(self, *_args) -> None:
        fm = self._box.fontMetrics()
        samples = [
            self._box.text(),
            self._box.prefix() + str(self._box.maximum()) + self._box.suffix(),
            self._box.prefix() + str(self._box.minimum()) + self._box.suffix(),
        ]
        width = max(fm.horizontalAdvance(s) for s in samples if s) + 14
        self._box.setFixedWidth(max(28, width))
        self.updateGeometry()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self._box.width() + 34, BUTTON_MIN_HEIGHT)

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802
        super().setEnabled(enabled)
        self._box.setEnabled(enabled)
        self._btn_up.setEnabled(enabled)
        self._btn_down.setEnabled(enabled)

    def setRange(self, minimum: int, maximum: int) -> None:  # noqa: N802
        self._box.setRange(minimum, maximum)
        self._sync_field_width()

    def setMinimum(self, minimum: int) -> None:  # noqa: N802
        self._box.setMinimum(minimum)
        self._sync_field_width()

    def setMaximum(self, maximum: int) -> None:  # noqa: N802
        self._box.setMaximum(maximum)
        self._sync_field_width()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if not self._box.hasFocus():
            event.ignore()
            return
        QSpinBox.wheelEvent(self._box, event)

    def focusInEvent(self, event) -> None:  # noqa: N802
        self._box.setFocus(Qt.FocusReason.OtherFocusReason)
        super().focusInEvent(event)

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._box, name)


class DateEdit(QWidget):
    """一体式日期框：外框 + 日期字 + 右侧日历图标（点任意处打开主题月历）。"""

    dateChanged = Signal(QDate)

    def __init__(self, parent=None, *, date: QDate | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DateEdit")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumHeight(BUTTON_MIN_HEIGHT + 4)
        self.setMaximumHeight(BUTTON_MIN_HEIGHT + 8)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._date = date if date is not None and date.isValid() else QDate.currentDate()

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 2, 0)
        lay.setSpacing(0)

        self._edit = QLineEdit()
        self._edit.setObjectName("DateEditField")
        self._edit.setReadOnly(True)
        self._edit.setFrame(False)
        self._edit.setPlaceholderText("yyyy-MM-dd")
        self._edit.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._edit.mousePressEvent = self._on_edit_press  # type: ignore[method-assign]
        lay.addWidget(self._edit, 1)

        self._btn = QToolButton()
        self._btn.setObjectName("DateEditButton")
        self._btn.setToolTip("选择日期")
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn.setAutoRaise(True)
        self._btn.setFixedSize(30, 28)
        self._btn.clicked.connect(self._open_picker)
        lay.addWidget(self._btn)

        self._sync_text()
        self._refresh_icon()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._refresh_icon()

    def _refresh_icon(self) -> None:
        try:
            from app.app_state import AppState
            from services.icon_registry import get_icon

            fg = str((AppState.get().palette or {}).get("text_primary") or "#333333")
            self._btn.setIcon(get_icon("calendar", color=fg, size=16, parent=self))
            self._btn.setIconSize(QSize(16, 16))
        except Exception:
            self._btn.setText("▾")

    def _on_edit_press(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self._open_picker()
            event.accept()
            return
        QLineEdit.mousePressEvent(self._edit, event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self._open_picker()
            event.accept()
            return
        super().mousePressEvent(event)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(168, BUTTON_MIN_HEIGHT + 4)

    def _sync_text(self) -> None:
        self._edit.setText(self._date.toString("yyyy-MM-dd"))

    def _open_picker(self) -> None:
        from PySide6.QtWidgets import QDialog

        from widgets.date_pick_dialog import DatePickDialog

        dlg = DatePickDialog(self.window(), initial=self._date, title="选择日期")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        picked = dlg.selected_qdate()
        if not picked.isValid():
            return
        self.setDate(picked)

    def date(self) -> QDate:
        return QDate(self._date)

    def setDate(self, value: QDate) -> None:  # noqa: N802
        if value is None or not value.isValid():
            value = QDate.currentDate()
        if value == self._date:
            self._sync_text()
            return
        self._date = QDate(value)
        self._sync_text()
        self.dateChanged.emit(self._date)

    def to_iso(self) -> str:
        return self._date.toString("yyyy-MM-dd")

    def set_iso(self, value: str) -> None:
        text = (value or "").strip()
        if not text:
            self.setDate(QDate.currentDate())
            return
        parsed = QDate.fromString(text, "yyyy-MM-dd")
        self.setDate(parsed if parsed.isValid() else QDate.currentDate())
