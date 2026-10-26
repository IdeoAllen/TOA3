# -*- coding: utf-8 -*-
"""官方示例：手机号脱敏。"""
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

_PHONE_RE = re.compile(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)")


def _mask(text: str) -> tuple[str, int]:
    count = 0

    def _repl(m: re.Match) -> str:
        nonlocal count
        count += 1
        return f"{m.group(1)}****{m.group(2)}"

    return _PHONE_RE.sub(_repl, text or ""), count


class ToolPhoneMaskPage(BasePage):
    page_id = "tool_phone_mask"
    page_title = "手机号脱敏"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        m = page_content_margins()
        outer.setContentsMargins(m[0], m[1], m[2], m[3])
        scroll = ScrollPage()
        outer.addWidget(scroll)

        scroll.add_widget(
            PageHeader(
                "手机号脱敏",
                "粘贴名单/备注 → 中国大陆 11 位手机号中间四位打码 → 复制结果。",
            )
        )
        src = FormSection("原文")
        src.add_widget(HintLabel("官方推荐小工具 · 仅本地处理，不联网。"))
        self._src = PlainTextEdit()
        self._src.setPlaceholderText("在此粘贴含手机号的文本…")
        self._src.setMinimumHeight(140)
        src.add_widget(self._src)
        scroll.add_widget(src)

        actions = FormSection("操作")
        ops = QHBoxLayout()
        btn = PrimaryButton("脱敏")
        btn.clicked.connect(self._on_run)
        ops.addWidget(btn)
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

    def _clear(self) -> None:
        self._src.clear()
        self._out.setPlainText("")
        self._status.setText("已清空")
        self.report_status("已清空", StatusLevel.INFO)

    def _on_run(self) -> None:
        text, n = _mask(self._src.toPlainText())
        self._out.setPlainText(text)
        self._status.setText(f"已处理 {n} 个手机号" if n else "未发现手机号")
        self.report_status(self._status.text(), StatusLevel.SUCCESS if n else StatusLevel.INFO)
