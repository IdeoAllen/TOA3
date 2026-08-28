# -*- coding: utf-8 -*-
"""办公链待投喂条：唯一闭环入口，不做第二聊天框。"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QWidget

from widgets import HintLabel, PrimaryButton, SecondaryButton


class FeedStrip(QWidget):
    apply_requested = Signal()
    dismissed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self._label = HintLabel("")
        lay.addWidget(self._label, 1)

        btn_apply = PrimaryButton("投喂到 Harness")
        btn_apply.clicked.connect(self.apply_requested.emit)
        lay.addWidget(btn_apply)

        btn_skip = SecondaryButton("忽略")
        btn_skip.clicked.connect(self.dismissed.emit)
        lay.addWidget(btn_skip)

    def set_preview(self, title: str, preview: str) -> None:
        text = preview if len(preview) <= 96 else preview[:96] + "…"
        self._label.setText(f"办公链 · {title}：{text}")
