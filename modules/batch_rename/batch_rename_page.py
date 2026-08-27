# -*- coding: utf-8 -*-
"""批量重命名页。"""
from __future__ import annotations

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_info, show_warning
from modules.batch_rename.rename_service import apply_rename, preview_rename
from widgets import (
    FormSection,
    HintLabel,
    LineEdit,
    PageHeader,
    PrimaryButton,
    ReadOnlyPlainTextEdit,
    ScrollPage,
    SecondaryButton,
    SpinBox,
)


class BatchRenamePage(BasePage):
    page_id = "batch_rename"
    page_title = "批量重命名"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll)
        scroll.add_widget(PageHeader("批量重命名", "按前缀/后缀/查找替换预览后执行；{n} 可作序号占位。"))

        box = FormSection("规则")
        row = QHBoxLayout()
        self._folder = LineEdit()
        row.addWidget(self._folder, 1)
        btn = SecondaryButton("选择目录")
        btn.clicked.connect(self._pick)
        row.addWidget(btn)
        box.add_layout(row)

        self._pattern = LineEdit("*")
        self._prefix = LineEdit()
        self._suffix = LineEdit()
        self._find = LineEdit()
        self._replace = LineEdit()
        self._start = SpinBox()
        self._start.setRange(0, 99999)
        self._start.setValue(1)
        box.add_widget(HintLabel("匹配 glob"))
        box.add_widget(self._pattern)
        box.add_widget(HintLabel("前缀（可用 {n}）"))
        box.add_widget(self._prefix)
        box.add_widget(HintLabel("后缀（可用 {n}）"))
        box.add_widget(self._suffix)
        box.add_widget(HintLabel("查找"))
        box.add_widget(self._find)
        box.add_widget(HintLabel("替换"))
        box.add_widget(self._replace)
        box.add_widget(HintLabel("起始序号"))
        box.add_widget(self._start)

        actions = QHBoxLayout()
        btn_prev = SecondaryButton("预览")
        btn_prev.clicked.connect(self._preview)
        actions.addWidget(btn_prev)
        btn_run = PrimaryButton("执行重命名")
        btn_run.clicked.connect(self._run)
        actions.addWidget(btn_run)
        actions.addStretch(1)
        box.add_layout(actions)

        self._preview_box = ReadOnlyPlainTextEdit()
        self._preview_box.setMinimumHeight(200)
        box.add_widget(self._preview_box)
        scroll.add_widget(box)
        self._pairs = []

    def _pick(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择目录")
        if d:
            self._folder.setText(d)

    def _preview(self) -> None:
        folder = self._folder.text().strip()
        if not folder:
            show_warning(self, "请选择目录。")
            return
        self._pairs = preview_rename(
            folder,
            pattern=self._pattern.text().strip() or "*",
            prefix=self._prefix.text(),
            suffix=self._suffix.text(),
            find=self._find.text(),
            replace=self._replace.text(),
            start_index=int(self._start.value()),
        )
        lines = [f"{a.name}  →  {b.name}" for a, b in self._pairs]
        self._preview_box.setPlainText("\n".join(lines) if lines else "（无变更）")
        self.report_status(f"预览 {len(self._pairs)} 项")

    def _run(self) -> None:
        if not self._pairs:
            self._preview()
        if not self._pairs:
            show_warning(self, "没有需要重命名的文件。")
            return
        ok, errors = apply_rename(self._pairs)
        msg = f"成功 {ok} 个"
        if errors:
            msg += "\n" + "\n".join(errors[:20])
        show_info(self, msg)
        self.report_status(f"重命名完成 {ok}", level=StatusLevel.SUCCESS)
        self._preview()

    def on_enter(self) -> None:
        self.report_status("批量重命名")
