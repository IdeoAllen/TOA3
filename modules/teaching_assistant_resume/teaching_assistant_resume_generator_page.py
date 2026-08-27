# -*- coding: utf-8 -*-
"""助教简历生成：单人 PPTX + Markdown 预览；Excel 批量。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QFormLayout, QHBoxLayout, QVBoxLayout, QWidget

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_saved, show_warning
from modules.teaching_assistant_resume.resume_pptx_generator import (
    FIELD_MAP,
    generate_resume_pptx,
    generate_resumes_from_excel,
)
from modules.teaching_assistant_resume.teaching_assistant_resume_service import FIELDS, render_resume_md
from services.storage_paths import list_module_templates, module_output_dir
from widgets import (
    FormSection,
    HintLabel,
    LineEdit,
    PageHeader,
    PlainTextEdit,
    PrimaryButton,
    ReadOnlyPlainTextEdit,
    ScrollPage,
    SecondaryButton,
    TabWidget,
)


class TeachingAssistantResumeGeneratorPage(BasePage):
    page_id = "teaching_assistant_resume"
    page_title = "助教简历生成"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._edits: dict[str, LineEdit | PlainTextEdit] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll)

        scroll.add_widget(
            PageHeader(
                "助教简历生成",
                "填写字段生成 PPTX（有模板时）并预览 Markdown；也可从 Excel 批量导出。",
            )
        )

        tpl_box = FormSection("模板")
        tpls = list_module_templates("teaching_assistant_resume")
        self._tpl_hint = HintLabel("")
        if tpls:
            self._tpl_hint.setText(f"当前模板：{tpls[0]}")
        else:
            self._tpl_hint.setText(
                "未找到 PPTX 模板（config/storage.yml → teaching_assistant_resume.templates）。"
                "将仅输出 Markdown / 纯文本。"
            )
        tpl_box.add_widget(self._tpl_hint)
        scroll.add_widget(tpl_box)

        self._tabs = TabWidget()
        scroll.add_widget(self._tabs)

        self._tabs.addTab(self._build_single_tab(), "单人生成")
        self._tabs.addTab(self._build_excel_tab(), "Excel 批量")

        out = FormSection("预览 / 日志")
        self._preview = ReadOnlyPlainTextEdit()
        self._preview.setMinimumHeight(160)
        out.add_widget(self._preview)
        scroll.add_widget(out)
        scroll.add_stretch(1)

        self.apply_page_focus_policy()

    def primary_focus_widget(self):
        return self._edits.get("name")

    def _build_single_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        form_box = FormSection("基本信息")
        host = QWidget()
        form = QFormLayout(host)
        for key, label in FIELDS:
            if key in {"experience", "skills", "summary"}:
                w: LineEdit | PlainTextEdit = PlainTextEdit()
                w.setMinimumHeight(72)
            else:
                w = LineEdit()
            self._edits[key] = w
            form.addRow(HintLabel(label), w)
        form_box.add_widget(host)
        lay.addWidget(form_box)

        actions = QHBoxLayout()
        btn = PrimaryButton("生成 PPTX 简历")
        btn.clicked.connect(self._on_generate)
        actions.addWidget(btn)
        btn_md = SecondaryButton("仅预览 Markdown")
        btn_md.clicked.connect(self._on_preview_md)
        actions.addWidget(btn_md)
        actions.addStretch(1)
        lay.addLayout(actions)
        lay.addStretch(1)
        return tab

    def _build_excel_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        box = FormSection("班级名单 Excel")
        row = QHBoxLayout()
        self._excel_path = LineEdit()
        self._excel_path.setReadOnly(True)
        row.addWidget(self._excel_path, 1)
        browse = SecondaryButton("浏览…")
        browse.clicked.connect(self._pick_excel)
        row.addWidget(browse)
        box.add_layout(row)
        cols = "、".join(FIELD_MAP.values())
        box.add_widget(
            HintLabel(
                f"列名建议：{cols}（也可用英文键 name/title/phone…）。每行一人。"
            )
        )
        lay.addWidget(box)

        actions = QHBoxLayout()
        btn = PrimaryButton("批量生成 PPTX")
        btn.clicked.connect(self._on_excel_batch)
        actions.addWidget(btn)
        actions.addStretch(1)
        lay.addLayout(actions)
        lay.addStretch(1)
        return tab

    def _collect(self) -> dict[str, str]:
        data: dict[str, str] = {}
        for key, w in self._edits.items():
            if isinstance(w, PlainTextEdit):
                data[key] = w.toPlainText().strip()
            else:
                data[key] = w.text().strip()
        return data

    def _pick_excel(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 Excel",
            "",
            "Excel (*.xlsx *.xls)",
        )
        if path:
            self._excel_path.setText(path)

    def _on_preview_md(self) -> None:
        data = self._collect()
        if not data.get("name"):
            show_warning(self, "请填写姓名。")
            return
        self._preview.setPlainText(render_resume_md(data))
        self.report_status("已预览 Markdown")

    def _on_generate(self) -> None:
        data = self._collect()
        if not data.get("name"):
            show_warning(self, "请填写姓名。")
            return

        def _run() -> None:
            self._preview.setPlainText(render_resume_md(data))
            out_dir = module_output_dir(self.page_id, create=True)
            paths = generate_resume_pptx(data, out_dir)
            msg = "已保存：\n" + "\n".join(str(p) for p in paths)
            self._preview.appendPlainText("\n\n" + msg)
            self.report_status("简历已生成", level=StatusLevel.SUCCESS)
            show_saved(self, msg, paths[0] if paths else out_dir)

        self.run_safe(_run, title="生成失败")

    def _on_excel_batch(self) -> None:
        excel = self._excel_path.text().strip()
        if not excel:
            show_warning(self, "请选择 Excel 文件。")
            return
        if not Path(excel).is_file():
            show_warning(self, "Excel 文件不存在。")
            return

        def _run() -> None:
            out_dir = module_output_dir(self.page_id, create=True)
            result = generate_resumes_from_excel(excel, out_dir)
            lines = [
                f"总数：{result.get('total', 0)}",
                f"成功：{result.get('success', 0)}",
                f"失败：{result.get('failed', 0)}",
                f"输出目录：{out_dir}",
            ]
            errs = result.get("errors") or []
            if errs:
                lines.append("错误：")
                lines.extend(f"  - {e}" for e in errs[:20])
            text = "\n".join(lines)
            self._preview.setPlainText(text)
            self.report_status(
                f"批量完成 成功 {result.get('success', 0)}",
                level=StatusLevel.SUCCESS,
            )
            show_saved(self, text, out_dir)

        self.run_safe(_run, title="批量生成失败")

    def on_enter(self) -> None:
        tpls = list_module_templates("teaching_assistant_resume")
        if tpls:
            self._tpl_hint.setText(f"当前模板：{tpls[0]}")
        self.report_status("助教简历生成")
