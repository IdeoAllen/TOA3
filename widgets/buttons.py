# -*- coding: utf-8 -*-
"""标准按钮（样式由全局 QSS + class 属性控制）。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from widgets.metrics import BUTTON_MIN_HEIGHT


def _no_focus_ring(btn: QPushButton) -> None:
    """去掉点击后的虚线焦点框。"""
    btn.setAttribute(Qt.WidgetAttribute.WA_MacShowFocusRect, False)


class PrimaryButton(QPushButton):
    """主操作按钮。"""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setProperty("class", "primary")
        self.setMinimumHeight(BUTTON_MIN_HEIGHT)
        _no_focus_ring(self)


class SecondaryButton(QPushButton):
    """次要按钮（默认样式）。"""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setMinimumHeight(BUTTON_MIN_HEIGHT)
        _no_focus_ring(self)


class DangerButton(QPushButton):
    """危险操作按钮。"""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setProperty("class", "danger")
        self.setMinimumHeight(BUTTON_MIN_HEIGHT)
        _no_focus_ring(self)


class MessageKindButton(QPushButton):
    """消息语义按钮（色与 MessageDialog 状态图标一致，见图知意）。"""

    _VALID = frozenset({"info", "warning", "error", "success", "confirm"})

    def __init__(self, text: str = "", *, kind: str = "info", parent=None) -> None:
        super().__init__(text, parent)
        k = kind if kind in self._VALID else "info"
        self.setProperty("class", f"msg-{k}")
        self.setMinimumHeight(BUTTON_MIN_HEIGHT)
        _no_focus_ring(self)


class InlineButton(QPushButton):
    """行内轻量按钮（同默认，语义别名）。"""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setMinimumHeight(BUTTON_MIN_HEIGHT)
        _no_focus_ring(self)
