# -*- coding: utf-8 -*-
"""未迁移 / 加载失败时的占位页。"""
from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout

from core.base_page import BasePage
from widgets.themed_labels import HintLabel, PageTitle


class StubPage(BasePage):
    def __init__(
        self,
        module_id: str,
        title: str,
        desc: str = "",
        parent=None,
        *,
        load_error: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.page_id = module_id
        self.page_title = title
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.addWidget(PageTitle(title))
        if load_error:
            body = HintLabel(
                f"「{title}」页面加载失败，已临时显示本占位页。\n"
                f"模块 ID：{module_id}\n"
                f"{desc}\n\n"
                f"原因：{load_error}\n\n"
                "请查看日志或联系开发修复后重启。"
            )
        else:
            body = HintLabel(
                f"「{title}」尚未接入业务页。\n"
                f"模块 ID：{module_id}\n"
                f"{desc}\n\n"
                "清单见 config/migration_manifest.yml。"
            )
        lay.addWidget(body)
        lay.addStretch(1)

    def on_enter(self) -> None:
        self.report_status(f"{self.page_title}（占位）")
