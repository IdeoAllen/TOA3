# -*- coding: utf-8 -*-
"""业务插件样例 · 示例问候。"""
from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout

from core.base_page import BasePage
from core.ui_spec import page_content_margins
from widgets import FormSection, HintLabel, PageTitle, PrimaryButton


class DemoHelloPage(BasePage):
    page_id = "demo_hello"
    page_title = "示例问候插件"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        m = page_content_margins()
        root = QVBoxLayout(self)
        root.setContentsMargins(*m)
        root.setSpacing(12)

        root.addWidget(PageTitle("示例问候插件"))
        box = FormSection("样例")
        box.add_widget(HintLabel("若你能打开本页，说明业务插件导入 → 侧栏挂载链路已通。"))
        btn = PrimaryButton("打个招呼")
        btn.clicked.connect(self._on_hello)
        box.add_widget(btn)
        root.addWidget(box)
        root.addStretch(1)
        self.apply_page_focus_policy()

    def _on_hello(self) -> None:
        self.report_status("你好 · TOA 业务插件已就绪")
