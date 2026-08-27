# -*- coding: utf-8 -*-
"""通用生成工具（轻量模板填充）。"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QVBoxLayout, QWidget

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_saved, show_warning
from modules.generic_generator_simple.generic_generator_simple_service import (
    extract_placeholders,
    render_template,
    write_outputs,
)
from services.storage_paths import module_output_dir
from widgets import (
    CheckBox,
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

_DEFAULT_TEMPLATE = (
    "标题：{{title}}\n"
    "负责人：{{owner}}\n"
    "日期：{{date}}\n"
    "摘要：{{summary}}\n"
)


class GenericGeneratorSimplePage(BasePage):
    page_id = "generic_generator_simple"
    page_title = "通用生成工具"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._field_edits: dict[str, LineEdit] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll)

        scroll.add_widget(
            PageHeader(
                "通用生成工具",
                "用 {{占位符}} 模板 + 字段填写，生成 txt/json。",
            )
        )

        tpl_box = FormSection("模板")
        self._template = PlainTextEdit(_DEFAULT_TEMPLATE)
        self._template.setMinimumHeight(120)
        tpl_box.add_widget(self._template)
        tpl_box.add_widget(HintLabel("占位符格式：{{name}}。修改模板后点「刷新字段」。"))
        scroll.add_widget(tpl_box)

        self._fields_box = FormSection("字段")
        self._fields_host = QWidget()
        self._fields_form = QFormLayout(self._fields_host)
        self._fields_box.add_widget(self._fields_host)
        scroll.add_widget(self._fields_box)

        self._as_json = CheckBox("同时输出 JSON")
        self._as_json.setChecked(True)
        scroll.add_widget(self._as_json)

        actions = QHBoxLayout()
        btn_refresh = SecondaryButton("刷新字段")
        btn_refresh.clicked.connect(self._rebuild_fields)
        actions.addWidget(btn_refresh)
        btn_go = PrimaryButton("生成")
        btn_go.clicked.connect(self._on_generate)
        actions.addWidget(btn_go)
        actions.addStretch(1)
        scroll.add_layout(actions)

        out = FormSection("预览 / 结果")
        self._preview = ReadOnlyPlainTextEdit()
        self._preview.setMinimumHeight(140)
        out.add_widget(self._preview)
        scroll.add_widget(out)
        scroll.add_stretch(1)

        self._rebuild_fields()

    def _rebuild_fields(self) -> None:
        while self._fields_form.rowCount():
            self._fields_form.removeRow(0)
        self._field_edits.clear()
        keys = extract_placeholders(self._template.toPlainText())
        if not keys:
            self._fields_form.addRow(HintLabel("模板中未检测到 {{占位符}}"))
            return
        for key in keys:
            edit = LineEdit()
            if key == "date":
                edit.setText(datetime.now().strftime("%Y-%m-%d"))
            self._field_edits[key] = edit
            self._fields_form.addRow(HintLabel(key), edit)

    def _collect(self) -> dict[str, str]:
        return {k: e.text().strip() for k, e in self._field_edits.items()}

    def _on_generate(self) -> None:
        tpl = self._template.toPlainText()
        if not tpl.strip():
            show_warning(self, "模板不能为空。")
            return

        def _run() -> None:
            values = self._collect()
            text = render_template(tpl, values)
            self._preview.setPlainText(text)
            out_dir = module_output_dir(self.page_id, create=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            paths = write_outputs(
                text,
                out_dir,
                basename=f"gen_{stamp}",
                as_json=self._as_json.isChecked(),
                meta={"values": values},
            )
            msg = "已生成：\n" + "\n".join(str(p) for p in paths)
            self.report_status("生成完成", level=StatusLevel.SUCCESS)
            show_saved(self, msg, paths[0] if paths else out_dir)

        self.run_safe(_run, title="生成失败")

    def on_enter(self) -> None:
        self.report_status("通用生成工具")
