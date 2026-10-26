# -*- coding: utf-8 -*-
"""官方示例：会议要点整理。"""
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


def _bullets(text: str) -> list[str]:
    out: list[str] = []
    for raw in (text or "").splitlines():
        s = raw.strip()
        if not s:
            continue
        s = re.sub(r"^[\d]+[\.\)、]\s*", "", s)
        s = re.sub(r"^[\-\*•◦▪]\s*", "", s)
        s = re.sub(r"^【.*?】\s*", "", s)
        if s:
            out.append(s)
    # 去重保序
    seen: set[str] = set()
    uniq: list[str] = []
    for line in out:
        if line in seen:
            continue
        seen.add(line)
        uniq.append(line)
    return uniq


class ToolMeetBulletsPage(BasePage):
    page_id = "tool_meet_bullets"
    page_title = "会议要点整理"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        m = page_content_margins()
        outer.setContentsMargins(m[0], m[1], m[2], m[3])
        scroll = ScrollPage()
        outer.addWidget(scroll)

        scroll.add_widget(
            PageHeader(
                "会议要点整理",
                "粘贴杂乱笔记 → 去空行/序号/书名号噪音 → 输出编号要点，便于纪要落盘。",
            )
        )
        src = FormSection("会议笔记")
        src.add_widget(HintLabel("官方推荐小工具 · 仅本地处理，不联网。"))
        self._src = PlainTextEdit()
        self._src.setPlaceholderText("粘贴会议录音转写或手写要点…")
        self._src.setMinimumHeight(140)
        src.add_widget(self._src)
        scroll.add_widget(src)

        actions = FormSection("操作")
        ops = QHBoxLayout()
        btn = PrimaryButton("整理要点")
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

        out = FormSection("要点列表")
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
        lines = _bullets(self._src.toPlainText())
        numbered = "\n".join(f"{i}. {line}" for i, line in enumerate(lines, 1))
        self._out.setPlainText(numbered)
        self._status.setText(f"共 {len(lines)} 条要点" if lines else "没有可用要点")
        self.report_status(self._status.text(), StatusLevel.SUCCESS if lines else StatusLevel.INFO)
