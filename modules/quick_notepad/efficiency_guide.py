# -*- coding: utf-8 -*-
"""记事效率指南：语法与快捷键，可收起。"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout

from widgets import HintLabel, SecondaryButton, SectionTitle

GUIDE_TEXT = (
    "编辑：所见即所得，写下即版式。\n"
    "源码：直接改 Markdown。"
    "# 标题 · **加粗** · *斜体* · ~~删除线~~ · ==高亮== · `行内代码` · "
    "``` 代码块 · - 列表 · - [ ] 待办 · > 引用 · | 表格 · ```mermaid 图表\n"
    "预览：只读纸面。\n"
    "Ctrl+S 保存 · Ctrl+N 新建 · Ctrl+B 加粗 · Ctrl+I 斜体 · Ctrl+K 链接 · Ctrl+F 查找。\n"
    "行首输入 # 、- 、1. 、> 再按空格，直接变成标题、列表或引用。\n"
    "更多里「导入 Markdown」，或把 .md 拖进窗口。"
)


class EfficiencyGuide(QFrame):
    """底栏可展开的语法说明。"""

    hide_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("NotepadEfficiencyGuide")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(4)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        title = SectionTitle("效率指南")
        head.addWidget(title, 1)
        close = SecondaryButton("收起")
        close.setToolTip("收起效率指南")
        close.clicked.connect(self.hide_requested.emit)
        head.addWidget(close)
        lay.addLayout(head)
        body = HintLabel(GUIDE_TEXT)
        body.setWordWrap(True)
        lay.addWidget(body)
