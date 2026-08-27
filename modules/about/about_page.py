# -*- coding: utf-8 -*-
"""关于页（兼容菜单登记；实际由顶栏 AboutDialog 弹窗展示）。"""
from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout

from core.base_page import BasePage
from widgets import HintLabel, PageTitle, ScrollPage


class AboutPage(BasePage):
    """保留模块登记；壳层 navigate(__about__) 已改弹窗，本页一般不进入。"""

    page_id = "__about__"
    page_title = "关于"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll)
        scroll.content_layout.addWidget(PageTitle("关于"))
        scroll.content_layout.addWidget(
            HintLabel("请从顶栏「关于」打开弹窗查看产品信息。")
        )
        scroll.content_layout.addStretch(1)
        self.apply_standard_page_layout()
