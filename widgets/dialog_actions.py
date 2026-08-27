# -*- coding: utf-8 -*-
"""弹窗底部按钮行。"""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QWidget

from widgets.buttons import PrimaryButton, SecondaryButton


class DialogButtonRow(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 8, 0, 0)
        self._lay.addStretch(1)

    def add_secondary(self, text: str, handler) -> SecondaryButton:
        btn = SecondaryButton(text)
        btn.clicked.connect(handler)
        self._lay.addWidget(btn)
        return btn

    def add_primary(self, text: str, handler) -> PrimaryButton:
        btn = PrimaryButton(text)
        btn.clicked.connect(handler)
        self._lay.addWidget(btn)
        return btn
