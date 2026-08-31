# -*- coding: utf-8 -*-
"""场景样例：日报助手骨架。"""
from __future__ import annotations

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.ui_spec import page_content_margins
from widgets import (
    DateEdit,
    FormSection,
    HintLabel,
    LineEdit,
    PageHeader,
    PlainTextEdit,
    PrimaryButton,
    ReadOnlyPlainTextEdit,
    ScrollPage,
    SecondaryButton,
    SemanticLabel,
)


class ScenarioDailyReportPage(BasePage):
    page_id = "scenario_daily_report"
    page_title = "场景 · 日报助手"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        m = page_content_margins()
        outer.setContentsMargins(m[0], m[1], m[2], m[3])
        scroll = ScrollPage()
        outer.addWidget(scroll)

        scroll.add_widget(
            PageHeader(
                "日报助手",
                "填写日期与要点 → 生成预览。复制为我的扩展后可用智能体加深（导出 Word 等）。",
            )
        )
        meta = FormSection("基本信息")
        meta.add_widget(HintLabel("场景模板 · 主路径可预览；复杂导出请复制后开发。"))
        row = QHBoxLayout()
        self._date = DateEdit(date=QDate.currentDate())
        self._date.setMaximumWidth(280)
        row.addWidget(self._date)
        self._title = LineEdit("")
        self._title.setPlaceholderText("今日主题 / 班次")
        self._title.setMaximumWidth(360)
        row.addWidget(self._title)
        row.addStretch(1)
        meta.add_layout(row)
        scroll.add_widget(meta)

        body = FormSection("今日要点")
        self._body = PlainTextEdit()
        self._body.setPlaceholderText("每行一条工作要点")
        self._body.setMinimumHeight(120)
        self._body.setMaximumHeight(200)
        body.add_widget(self._body)
        scroll.add_widget(body)

        actions = FormSection("操作")
        ops = QHBoxLayout()
        self._btn = PrimaryButton("生成日报预览")
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
        self._preview.setMinimumHeight(120)
        prev.add_widget(self._preview)
        scroll.add_widget(prev)
        scroll.add_stretch(1)
        self.apply_page_focus_policy()

    def primary_focus_widget(self):
        return self._title

    def focus_tab_widgets(self):
        return [self._date, self._title, self._body, self._btn]

    def _on_run(self) -> None:
        title = self._title.text().strip() or "工作日报"
        date_s = self._date.date().toString("yyyy-MM-dd")
        body = self._body.toPlainText().strip() or "（暂无要点）"
        text = f"# {title}\n\n日期：{date_s}\n\n## 要点\n\n{body}\n"
        self._preview.setPlainText(text)
        self._status.setText("已生成预览")
        self.report_status("日报预览已生成", level=StatusLevel.SUCCESS)
