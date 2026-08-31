# -*- coding: utf-8 -*-
"""系统 · 扩展：用户自建功能管理（产品方案 feature_id=user_extensions）。"""
from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from core.base_page import BasePage
from core.ui_spec import page_content_margins
from modules.user_extensions.extensions_section import ExtensionsSection
from widgets import PageHeader


class UserExtensionsPage(BasePage):
    page_id = "user_extensions"
    page_title = "扩展"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        m = page_content_margins()
        outer.setContentsMargins(m[0], m[1], m[2], m[3])
        outer.setSpacing(12)

        outer.addWidget(
            PageHeader(
                "扩展 · 增长中心",
                "本机自建与社区插件。「新增」写需求，智能体开发后挂到「业务」；可移除。",
            )
        )
        self._section = ExtensionsSection(self)
        outer.addWidget(self._section, 1)
        self.apply_page_focus_policy()

    def primary_focus_widget(self) -> QWidget | None:
        return self._section.primary_focus_widget()

    def focus_tab_widgets(self) -> list[QWidget]:
        w = self.primary_focus_widget()
        return [w] if w is not None else []

    def on_enter(self) -> None:
        self._section.reload()
        self.report_status("扩展")
