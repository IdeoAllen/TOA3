# -*- coding: utf-8 -*-
"""场景样例：粘贴整理骨架。"""
from __future__ import annotations

import re

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.ui_spec import page_content_margins
from widgets import (
    FormSection,
    HintLabel,
    PageHeader,
    PlainTextEdit,
    PrimaryButton,
    ReadOnlyPlainTextEdit,
    ScrollPage,
    SecondaryButton,
    SemanticLabel,
)


def _tidy(text: str) -> str:
    lines = []
    for raw in (text or "").splitlines():
        s = raw.strip()
        if not s:
            continue
        s = re.sub(r"^[\d]+[\.\)、]\s*", "", s)
        s = re.sub(r"^[\-\*•]\s*", "", s)
        if s:
            lines.append(s)
    return "\n".join(lines)


class ScenarioPasteTidyPage(BasePage):
    page_id = "scenario_paste_tidy"
    page_title = "场景 · 粘贴整理"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        m = page_content_margins()
        outer.setContentsMargins(m[0], m[1], m[2], m[3])
        scroll = ScrollPage()
        outer.addWidget(scroll)

        scroll.add_widget(
            PageHeader(
                "粘贴整理",
                "粘贴杂乱名单/备注 → 一键去空行与简单序号 → 预览结果。",
            )
        )
        src = FormSection("原文")
        src.add_widget(HintLabel("场景模板 · 复制后可用智能体加扣分备注等规则。"))
        self._src = PlainTextEdit()
        self._src.setPlaceholderText("在此粘贴…")
        self._src.setMinimumHeight(140)
        src.add_widget(self._src)
        scroll.add_widget(src)

        actions = FormSection("操作")
        ops = QHBoxLayout()
        self._btn = PrimaryButton("整理")
        self._btn.clicked.connect(self._on_run)
        ops.addWidget(self._btn)
        btn_clear = SecondaryButton("清空")
        btn_clear.clicked.connect(self._clear)
        ops.addWidget(btn_clear)
        ops.addStretch(1)
        self._status = SemanticLabel("就绪", kind="info")
        ops.addWidget(self._status)
        actions.add_layout(ops)
        scroll.add_widget(actions)

        out = FormSection("结果")
        self._out = ReadOnlyPlainTextEdit("")
        self._out.setMinimumHeight(140)
        out.add_widget(self._out)
        scroll.add_widget(out)
        scroll.add_stretch(1)
        self.apply_page_focus_policy()

    def primary_focus_widget(self):
        return self._src

    def focus_tab_widgets(self):
        return [self._src, self._btn]

    def _clear(self) -> None:
        self._src.setPlainText("")
        self._out.setPlainText("")

    def _on_run(self) -> None:
        result = _tidy(self._src.toPlainText())
        self._out.setPlainText(result or "（无有效行）")
        n = len([x for x in result.splitlines() if x.strip()]) if result else 0
        self._status.setText(f"已整理 {n} 行")
        self.report_status(f"粘贴整理完成 · {n} 行", level=StatusLevel.SUCCESS)
