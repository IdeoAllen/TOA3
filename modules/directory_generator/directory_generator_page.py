# -*- coding: utf-8 -*-
"""批量文件夹生成。"""
from __future__ import annotations

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_saved, show_warning
from modules.directory_generator.directory_generator_service import (
    DIRECTORY_TEMPLATES,
    create_directories,
    parse_names,
)
from widgets import (
    ComboBox,
    FormSection,
    HintLabel,
    LineEdit,
    PageHeader,
    PlainTextEdit,
    PrimaryButton,
    ReadOnlyPlainTextEdit,
    ScrollPage,
    SecondaryButton,
)

_TEMPLATES: dict[str, str] = {k: v[1] for k, v in DIRECTORY_TEMPLATES.items()}


class DirectoryGeneratorPage(BasePage):
    page_id = "directory_generator"
    page_title = "批量文件夹生成"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll)

        scroll.add_widget(
            PageHeader(
                "批量文件夹生成",
                "粘贴名单或选模板 → 预览 → 幂等创建（已存在跳过）。",
            )
        )

        path_box = FormSection("目标父目录")
        row = QHBoxLayout()
        self._parent = LineEdit()
        self._parent.setPlaceholderText("选择或粘贴父目录路径…")
        row.addWidget(self._parent, 1)
        btn_browse = SecondaryButton("浏览…")
        btn_browse.clicked.connect(self._browse)
        row.addWidget(btn_browse)
        path_box.add_layout(row)
        scroll.add_widget(path_box)

        tpl = FormSection("模板 / 名单")
        row_t = QHBoxLayout()
        self._tpl = ComboBox()
        self._tpl.setMinimumWidth(220)
        self._tpl.setMinimumContentsLength(14)
        for key, (label, _body) in DIRECTORY_TEMPLATES.items():
            self._tpl.addItem(label, key)
        self._tpl.currentIndexChanged.connect(self._apply_template)
        row_t.addWidget(self._tpl)
        btn_preview = SecondaryButton("预览树")
        btn_preview.clicked.connect(self._preview)
        row_t.addWidget(btn_preview)
        row_t.addStretch(1)
        tpl.add_layout(row_t)
        self._names = PlainTextEdit()
        self._names.setPlaceholderText("每行一个文件夹名，可从 Excel 粘贴名单…")
        self._names.setMinimumHeight(160)
        self._names.textChanged.connect(self._preview)
        tpl.add_widget(self._names)
        scroll.add_widget(tpl)

        actions = QHBoxLayout()
        btn_go = PrimaryButton("创建目录")
        btn_go.clicked.connect(self._on_create)
        actions.addWidget(btn_go)
        btn_clear = SecondaryButton("清空")
        btn_clear.clicked.connect(self._on_clear)
        actions.addWidget(btn_clear)
        actions.addStretch(1)
        scroll.add_layout(actions)

        log_box = FormSection("预览 / 结果")
        self._log = ReadOnlyPlainTextEdit()
        self._log.setMinimumHeight(120)
        log_box.add_widget(self._log)
        log_box.add_widget(HintLabel("已存在的同名目录会跳过，不会覆盖（可续跑）。"))
        scroll.add_widget(log_box)
        scroll.add_stretch(1)

    def _apply_template(self) -> None:
        key = str(self._tpl.currentData() or "blank")
        text = _TEMPLATES.get(key, "")
        if text:
            self._names.setPlainText(text)
        self._preview()

    def _preview(self) -> None:
        parent = self._parent.text().strip() or "（未选父目录）"
        names = parse_names(self._names.toPlainText())
        if not names:
            self._log.setPlainText("（名单为空）")
            return
        lines = [f"{parent}/"]
        for n in names:
            lines.append(f"  └ {n}/")
        self._log.setPlainText("\n".join(lines))

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择父目录")
        if path:
            self._parent.setText(path)
            self._preview()

    def _on_clear(self) -> None:
        self._names.clear()
        self._log.clear()

    def _on_create(self) -> None:
        parent = self._parent.text().strip()
        names = parse_names(self._names.toPlainText())
        if not parent:
            show_warning(self, "请先选择目标父目录。")
            return
        if not names:
            show_warning(self, "请至少输入一个文件夹名称。")
            return

        def _run() -> None:
            result = create_directories(parent, names)
            self._log.setPlainText(result.summary)
            self.report_status(
                f"已创建 {len(result.created)} 个目录",
                level=StatusLevel.SUCCESS if not result.errors else StatusLevel.WARNING,
            )
            show_saved(self, result.summary.split("\n", 1)[0], parent)

        self.run_safe(_run, title="创建目录失败")

    def on_enter(self) -> None:
        self._preview()
        self.report_status("批量文件夹生成 · 粘贴名单或选模板")
