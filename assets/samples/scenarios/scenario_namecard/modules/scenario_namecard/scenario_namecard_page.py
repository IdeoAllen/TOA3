# -*- coding: utf-8 -*-
"""场景样例：简易台卡文案骨架。"""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.ui_spec import page_content_margins
from widgets import (
    FormSection,
    HintLabel,
    LineEdit,
    PageHeader,
    PrimaryButton,
    ReadOnlyPlainTextEdit,
    ScrollPage,
    SecondaryButton,
    SemanticLabel,
)


class ScenarioNamecardPage(BasePage):
    page_id = "scenario_namecard"
    page_title = "场景 · 简易台卡"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        m = page_content_margins()
        outer.setContentsMargins(m[0], m[1], m[2], m[3])
        scroll = ScrollPage()
        outer.addWidget(scroll)

        scroll.add_widget(
            PageHeader(
                "简易台卡",
                "填写姓名与职务 → 生成台卡文案预览。批量/PPT 请复制扩展后开发或用官方桌卡工具。",
            )
        )
        form = FormSection("嘉宾信息")
        form.add_widget(HintLabel("场景模板 · L1 文案预览。"))
        row = QHBoxLayout()
        self._name = LineEdit("")
        self._name.setPlaceholderText("姓名")
        self._name.setMaximumWidth(240)
        row.addWidget(self._name)
        self._role = LineEdit("")
        self._role.setPlaceholderText("职务 / 单位")
        self._role.setMaximumWidth(360)
        row.addWidget(self._role)
        row.addStretch(1)
        form.add_layout(row)
        scroll.add_widget(form)

        actions = FormSection("操作")
        ops = QHBoxLayout()
        self._btn = PrimaryButton("生成台卡文案")
        self._btn.clicked.connect(self._on_run)
        ops.addWidget(self._btn)
        btn_clear = SecondaryButton("清空")
        btn_clear.clicked.connect(lambda: self._preview.setPlainText(""))
        ops.addWidget(btn_clear)
        ops.addStretch(1)
        self._status = SemanticLabel("就绪", kind="info")
        ops.addWidget(self._status)
        actions.add_layout(ops)
        scroll.add_widget(actions)

        prev = FormSection("预览")
        self._preview = ReadOnlyPlainTextEdit("")
        self._preview.setMinimumHeight(100)
        prev.add_widget(self._preview)
        scroll.add_widget(prev)
        scroll.add_stretch(1)
        self.apply_page_focus_policy()

    def primary_focus_widget(self):
        return self._name

    def focus_tab_widgets(self):
        return [self._name, self._role, self._btn]

    def _on_run(self) -> None:
        name = self._name.text().strip() or "（姓名）"
        role = self._role.text().strip() or "（职务）"
        text = f"╔══════════════╗\n║  {name}\n║  {role}\n╚══════════════╝\n"
        self._preview.setPlainText(text)
        self._status.setText("已生成文案")
        self.report_status("台卡文案已生成", level=StatusLevel.SUCCESS)
