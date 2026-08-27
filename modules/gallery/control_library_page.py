# -*- coding: utf-8 -*-
"""控件库页（嵌入主壳）。"""
from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout

from core.base_page import BasePage
from modules.gallery.control_library_content import build_control_library_content


class ControlLibraryPage(BasePage):
    page_id = "theme_preview"
    page_title = "控件库（主题预览）"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(build_control_library_content(self))
