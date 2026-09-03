# -*- coding: utf-8 -*-
"""Harness 原版 Web 内嵌区（无多余框线，Guest 全宽）。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from widgets import HintLabel


class HarnessWebHost(QWidget):
    """Guest：内嵌 Web 或浏览器模式占位。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._embed_slot = QWidget()
        self._embed_slot.setObjectName("HarnessWebEmbedSlot")
        lay.addWidget(self._embed_slot, 1)

        self._external_hint = HintLabel("已在浏览器打开 · 点工具栏「内嵌」收回套件内")
        self._external_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._external_hint.hide()
        lay.addWidget(self._external_hint, 1)

    def embed_container(self) -> QWidget:
        return self._embed_slot

    def set_url_text(self, url: str) -> None:
        """保留接口；地址改由页状态栏展示，不占用主视觉区。"""
        self._url = url

    def show_embed_mode(self) -> None:
        self._embed_slot.show()
        self._external_hint.hide()

    def show_browser_mode(self) -> None:
        self._embed_slot.hide()
        self._external_hint.show()
